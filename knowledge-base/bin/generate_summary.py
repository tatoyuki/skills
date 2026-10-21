#!/usr/bin/env python3
"""generate_summary.py — documents の summary と ingest_priority を LLM API で生成する。

モード（どちらか選択）:
- 既定（生成）: 元ファイルを読み、summary と ingest_priority（0〜3。将来の作業で再利用できる
  失敗・知見・手順の価値）を 1 回の LLM 呼び出しで生成する。
- --score-only: すでに summary があるレコード向け。既存 summary だけから ingest_priority を
  バッチ採点する（対象 summary <> '' AND ingest_priority IS NULL。summary は再生成しない）。

対象行（生成モード）: summary が空、または modified_at > summary_at（生成後にファイルが更新された行）。
生成に使用したファイルの mtime を summary_at に保存し、2回目以降は差分のある行だけ再生成する。
生成時のファイル内容 hash（summary_hash 列、xxh64）と現在の hash が一致する行は mtime のみの偽更新とみなし、
再生成しない（summary_at だけ更新）。xxhsum が無い環境ではこの判定は無効で従来動作。
ignore_path に該当する path（ファイルは完全一致、ディレクトリは配下すべて）は対象行からスキップする。

LLM 接続は adapters パッケージ（bin/adapters/）に切り出している。接続方式（adapter / base_url /
model / timeout）はスキルディレクトリの config.toml [llm] で設定する。
CLI オプション --adapter openai_compatible | opencode_cli が config.toml より優先（既定は config.toml）。

並列: --parallel N（既定 1）。N>1 のときスレッド数ぶん同時生成する。DB 更新はスレッドごとに別接続（thread-local）で commit する。

使い方:
    python3 generate_summary.py                 # 対象行を生成（既定 1 = 逐次）
                                                # 実行中に q キー（Ctrl-C/Ctrl-D も）で
                                                # 処理中のファイルを完了させた後、停止する
    python3 generate_summary.py --limit N       # 処理上限（既定 0 = 無制限）
    python3 generate_summary.py --parallel N    # 並列数（既定 1）
    python3 generate_summary.py --dry-run       # 対象件数とサンプルのみ表示
    python3 generate_summary.py --adapter NAME   # openai_compatible | opencode_cli（既定 config.toml [llm]）
    python3 generate_summary.py --base-url URL   # openai_compatible のみ（既定 config.toml [llm]）
    python3 generate_summary.py --model MODEL    # 既定 config.toml [llm] → アダプタ既定
    python3 generate_summary.py --db FILE        # DB パス
    python3 generate_summary.py --max-chars N    # プロンプトに載せる本文の上限（既定 8000。0 で無制限）
    python3 generate_summary.py --timeout SEC     # リクエストタイムアウト（既定 120）
    python3 generate_summary.py --score-only      # 既存 summary から ingest_priority のみ採点（summary 生成なし）
    python3 generate_summary.py --batch N         # --score-only のバッチサイズ（既定 20）

1件ごとに 読み込み → 生成 → DB 更新（commit） までのミリ秒を出力する。
完了時に 更新件数・1件平均ミリ秒・合計秒数を出力する。
"""
import argparse
import json
import os
import sqlite3
import sys
import threading
import time

from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbase  # noqa: E402

# LLM の生成設定（スクリプト側の設定。接続設定は config.toml [llm] と adapters/openai_compatible.py の既定値）。
# reasoning はオフ（ユーザー指示 2026-10-12）
# max_tokens: 暴走出力対策（実測で 1.3 万字の summary が発生。decode ~40 tok/s のため 1 件で数分になった）。
# 100〜200 字の日本語 summary + JSON で 400 token 程度なので 640 で十分。
LLM_BODY = {
    "reasoning_effort": "none",
    "reasoning_budget_tokens": 0,
    "temperature": 0.5,
    "top_p": 0.95,
    "max_tokens": 640,
}

PROMPT_TEMPLATE = """以下のMarkdownファイルを、後でAIが関連ファイルを検索するために要約してください。

次の情報を簡潔に含めてください。
- このファイルが何について書かれているか
- 何を解決・説明・記録するファイルか
- 重要な技術名、製品名、コマンド、概念
- 特に検索語になりそうな語

原文にない情報は追加しないでください。

あわせて、このファイルが将来の作業で再利用できる失敗・知見・手順の価値を ingest_priority で採点してください。
- 3: 再利用可能な失敗（症状・原因・対策）や手順・知見が明確
- 2: 関連する知見・手順を含む
- 1: 価値は弱いが完全に無価値ではない
- 0: 日次作業記録・一時的なメモなど再利用価値がない

出力は JSON のみにしてください。形式:
{{"summary": "<100〜200文字程度の日本語の要約>", "priority": <0|1|2|3>}}

ファイル内容:
{content}
"""

SCORE_PROMPT_TEMPLATE = """あなたは知識ベースの採点エージェントです。以下の各ファイルの要約を読み、
将来の作業で再利用できる失敗・知見・手順の価値を ingest_priority で採点してください。

採点基準:
- 3: 再利用可能な失敗（症状・原因・対策）や手順・知見が明確
- 2: 関連する知見・手順を含む
- 1: 価値は弱いが完全に無価値ではない
- 0: 日次作業記録・一時的なメモなど再利用価値がない

出力は JSON 配列のみにしてください。形式: [{{"id": <番号>, "priority": <0|1|2|3>}}, ...]
すべての番号を1回ずつ含めてください。

ファイル:
{items}
"""


def clean_output(text):
    """本文前の見出し（例: **要約**）は検索用テキストとして不要なので除く。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and lines[0].strip() in ("**要約**", "要約:", "要約"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def parse_summary_output(text):
    """LLM 出力から (summary, priority) を抽出する。priority が不正な値、または JSON でない
    旧形式出力は本文全体を summary とみなし priority None（DB では NULL）。"""
    t = clean_output(text)
    if not t:
        return None, None
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(t[start:end + 1])
        except json.JSONDecodeError:
            obj = None
        if obj is not None:
            summary = clean_output(str(obj.get("summary") or ""))
            pr = obj.get("priority")
            priority = pr if isinstance(pr, int) and 0 <= pr <= 3 else None
            if summary:
                return summary, priority
    return t, None


_thread_local = threading.local()


def get_thread_con(db):
    """スレッドごとの DB 接続（thread-local）。sqlite3 接続はスレッド間で共有しない。"""
    if not hasattr(_thread_local, "con"):
        _thread_local.con = sqlite3.connect(db)
    return _thread_local.con


def process_row(i, total, p, modified_at, file_hash, args, adapter):
    """1件分: 読み込み → 生成 → DB 更新（commit）。(kind, i, p, detail, elapsed_ms) を返す。"""
    t0 = time.perf_counter()
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as exc:
        return ("error", i, p, str(exc), 0)

    if args.max_chars and len(content) > args.max_chars:
        content = content[:args.max_chars]

    text, err = adapter.chat(PROMPT_TEMPLATE.format(content=content))
    if not err:
        summary, priority = parse_summary_output(text)
        if not summary:
            err = "empty summary"
    con = get_thread_con(args.db)
    if err:
        # 失敗フラグ: エラーメッセージと失敗時点の hash を保存。内容が変わるまで再試行しない
        con.execute(
            "UPDATE documents SET summary_error = ?, summary_error_hash = ? WHERE path = ?",
            (err, file_hash, p),
        )
        con.commit()
        return ("error", i, p, err, 0)

    con.execute(
        "UPDATE documents SET summary = ?, summary_at = ?, summary_hash = ?, ingest_priority = ?, "
        "summary_error = '', summary_error_hash = '' WHERE path = ?",
        (summary, modified_at, file_hash, priority, p),
    )
    con.commit()
    return ("ok", i, p, f"priority={priority}", int((time.perf_counter() - t0) * 1000))


def score_batch(batch, adapter):
    """--score-only 用: [(path, summary)] を1回の LLM 呼び出しで採点し {path: priority} を返す。
    失敗時は (None, error)。返されなかった行は NULL のまま（再実行で再採点）。"""
    items = "\n\n".join(f"[{n}] {p}\n要約: {s}" for n, (p, s) in enumerate(batch, 1))
    text, err = adapter.chat(SCORE_PROMPT_TEMPLATE.format(items=items))
    if err:
        return None, err
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None, "no json array"
    try:
        arr = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        return None, f"json: {exc}"
    if not isinstance(arr, list):
        return None, "not a list"
    scored = {}
    for entry in arr:
        if not isinstance(entry, dict):
            continue
        n, pr = entry.get("id"), entry.get("priority")
        if isinstance(n, int) and 1 <= n <= len(batch) and isinstance(pr, int) and 0 <= pr <= 3:
            scored[batch[n - 1][0]] = pr
    if not scored:
        return None, "no valid entries"
    return scored, None


def main():
    parser = argparse.ArgumentParser(description="documents.summary を LLM API で生成する")
    parser.add_argument("--db", default=kbase.DB_DEFAULT, help="DB パス")
    parser.add_argument("--adapter", default=None,
                        choices=["openai_compatible", "opencode_cli"],
                        help="LLM 接続アダプタ（既定 config.toml [llm]）")
    parser.add_argument("--base-url", default=None,
                        help="openai_compatible のベースURL（既定 config.toml [llm]）")
    parser.add_argument("--model", default=None, help="モデル名（既定 config.toml [llm] → アダプタ既定）")
    parser.add_argument("--limit", type=int, default=0, help="処理上限（0 は無制限）")
    parser.add_argument("--parallel", type=int, default=1, help="並列数（既定 1）")
    parser.add_argument("--max-chars", type=int, default=8000,
                        help="プロンプトの本文上限（0 は無制限。既定 8000。decode/prefill が遅い環境では 20KB 超ファイル 1 件で数分かかるため既定で切り詰める）")
    parser.add_argument("--timeout", type=int, default=None,
                        help="リクエストタイムアウト秒（既定 config.toml [llm] → 120）")
    parser.add_argument("--dry-run", action="store_true", help="生成しない")
    parser.add_argument("--score-only", action="store_true",
                        help="既存 summary から ingest_priority のみ採点（summary 生成なし）")
    parser.add_argument("--batch", type=int, default=20, help="--score-only のバッチサイズ（既定 20）")
    args = parser.parse_args()

    adapter = kbase.create_llm_adapter(args.adapter, args.base_url, args.model,
                                       args.timeout, body=LLM_BODY)

    con = sqlite3.connect(args.db)
    con.execute(kbase.IGNORE_SCHEMA)
    kbase.ensure_summary_hash(con)
    kbase.ensure_ingest_priority(con)
    kbase.ensure_error_columns(con)
    files, dirs = kbase.load_ignore(con)

    if args.score_only:
        rows = [row for row in con.execute(
            "SELECT path, summary FROM documents WHERE summary <> '' AND ingest_priority IS NULL ORDER BY id"
        ).fetchall() if not kbase.is_ignored(row[0], files, dirs)]
        if args.limit:
            rows = rows[:args.limit]
        print(f"score targets: {len(rows)}")
        print(f"batch: {args.batch}")
        if args.dry_run:
            for p, _s in rows[:5]:
                print(f"  {p}")
            con.close()
            return
        scored_total = 0
        batch_errors = 0
        started = time.perf_counter()
        stop_requested = kbase.setup_stop_key()
        print("キー入力: q で処理中のバッチ完了後、停止")
        for bi in range(0, len(rows), args.batch):
            if stop_requested():
                print(f"stop: {bi}/{len(rows)} 件で停止（残りは未処理）")
                break
            batch = rows[bi:bi + args.batch]
            t0 = time.perf_counter()
            scored, err = score_batch(batch, adapter)
            elapsed = int((time.perf_counter() - t0) * 1000)
            if err:
                batch_errors += 1
                print(f"[batch {bi // args.batch + 1}] failed ({elapsed} ms): {err}")
                continue
            for path, pr in scored.items():
                con.execute("UPDATE documents SET ingest_priority = ? WHERE path = ?", (pr, path))
            con.commit()
            scored_total += len(scored)
            print(f"[batch {bi // args.batch + 1}] scored: {len(scored)}/{len(batch)}  {elapsed} ms")
        print(f"scored: {scored_total}")
        print(f"unscored: {len(rows) - scored_total}")
        print(f"batch errors: {batch_errors}")
        print(f"total: {time.perf_counter() - started:.1f} s")
        con.close()
        return

    rows = con.execute(
        "SELECT path, modified_at, summary, summary_hash, summary_error, summary_error_hash "
        "FROM documents WHERE summary = '' OR modified_at > summary_at ORDER BY id"
    ).fetchall()
    ignored = sum(1 for row in rows if kbase.is_ignored(row[0], files, dirs))
    rows = [row for row in rows if not kbase.is_ignored(row[0], files, dirs)]

    # hash 一致（mtime 偽更新）の行は再生成せず summary_at だけ更新する。
    # ただし summary が空の行は hash 一致でも生成対象（要約自体が存在しない）。
    # 前回失敗行（summary_error 一致）は内容が変わるまで再試行しない。
    hashes = kbase.hash_files([row[0] for row in rows])
    skip_rows = []
    regen_rows = []
    error_skip = []
    for p, modified_at, summary, summary_hash, summary_error, summary_error_hash in rows:
        h = hashes.get(p, "")
        if summary and h and h == summary_hash:
            skip_rows.append((p, modified_at))
        elif summary_error and h and h == summary_error_hash:
            error_skip.append(p)
        else:
            regen_rows.append((p, modified_at, h))

    if args.limit:
        regen_rows = regen_rows[:args.limit]

    print(f"targets: {len(rows)}")
    print(f"ignored: {ignored}")
    print(f"hash-skip: {len(skip_rows)}")
    print(f"error-skip: {len(error_skip)}")
    if args.dry_run:
        for row in rows[:5]:
            print(f"  {row[0]}")
        return

    # hash-skip 行は summary_at を現在 mtime へ進めるだけ（summary は保持）。
    for p, modified_at in skip_rows:
        con.execute("UPDATE documents SET summary_at = ? WHERE path = ?", (modified_at, p))
    con.commit()

    generated = 0
    errors = 0
    sum_ms = 0
    started = time.perf_counter()
    total = len(regen_rows)
    print(f"parallel: {args.parallel}")
    stop_requested = kbase.setup_stop_key()
    print("キー入力: q で処理中のファイルを完了後、停止")
    stop_noted = False
    cancelled = 0
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = [pool.submit(process_row, i, total, p, mtime, h, args, adapter)
                   for i, (p, mtime, h) in enumerate(regen_rows, 1)]
        # 出力は完了順（並列のため index 順ではない）
        for fut in as_completed(futures):
            if fut.cancelled():
                continue
            if not stop_noted and stop_requested():
                stop_noted = True
                cancelled = sum(1 for f in futures if f.cancel())
                print(f"stop: 処理中の分を完了後、停止（待機 {cancelled} 件は未処理）")
            kind, i, p, detail, elapsed_ms = fut.result()
            if kind == "error":
                errors += 1
                print(f"[{i}/{total}] failed: {p}: {detail}")
            else:
                generated += 1
                sum_ms += elapsed_ms
                suffix = f"  {detail}" if detail else ""
                print(f"[{i}/{total}] {elapsed_ms} ms{suffix}  {p}")

    total_seconds = time.perf_counter() - started
    print(f"updated: {generated}")
    print(f"errors: {errors}")
    if generated:
        print(f"average: {sum_ms / generated:.0f} ms")
    else:
        print("average: -")
    print(f"total: {total_seconds:.1f} s")
    con.close()


if __name__ == "__main__":
    main()
