#!/usr/bin/env python3
"""create_pattern.py — documents の未確認ファイルから Wiki Pattern を生成する。

対象行: ingest_status = ''（内容未確認）の行 + patterned / not_needed の行で
modified_at > ingested_at かつ hash <> ingested_hash（更新ファイルの再Ingest。not_needed も再評価）。
処理順序: 未確認行（ingest_status=''）優先 → ingest_priority 高い順（0〜3。未採点 NULL は最後）→
modified_at 古い順。ingest_priority は generate_summary.py が採点（summary 生成時 または --score-only）。
ignore_path 該当と wiki/ 配下自体はスキップ
（wiki/ の Pattern ページを pattern 化しない。循環回避）。--path-like でパスを絞り込める。
1行ごとに LLM で判定し、patterned なら wiki へ書き込み、not_needed wiki は触らない。
patterned は 1 ファイルで複数 Pattern を返せる（patterns 配列。独立した知見ごとに分割。
1 エントリ = 1 ページへの追記/作成。不正エントリはスキップし有効なものだけ書き込む）。
書き込み先は LLM が返す領域ディレクトリ dir（例: go/bubbletea。技術/プロジェクト階層、
最大3階層）。不正値は wiki 直下にフォールバック。log.md は wiki 直下1本のまま。
完了した行は ingest_status / ingested_at / ingested_hash（Ingest 時点 hash）を更新する。

原則: summary は query（検索）に用いるもの。Ingest の内容確認は本文全体を読んで行う。
本スクリプトは LLM に本文全体を渡す（既定は無制限。--max-chars は緊急時の切り詰め用）。

generate_summary.py と同一流儀: LLM 接続は adapters パッケージ（bin/adapters/）に切り出している。
接続方式（adapter / base_url / model / timeout）はスキルディレクトリの config.toml [llm] で設定する。
CLI オプション --adapter openai_compatible | opencode_cli が config.toml より優先（既定は config.toml）。
書き込みは wiki/log.md・同一ページを共有するため直列実行（並列化しない）。

hash-skip: 更新候補行のうち modified_at > ingested_at だが hash = ingested_hash の行
（touch / cp / git checkout の偽更新）は LLM を呼ばず ingested_at = modified_at のみ UPDATE。
クラッシュ復帰は行わない（2026-10-12 決定）。再実行で生じた重複セクションは Lint で検出・削除。

使い方:
    python3 create_pattern.py                 # 未確認行を全て処理（既定無制限）
                                              # 実行中に q キー（Ctrl-C/Ctrl-D も）で
                                              # 処理中のファイルを完了させた後、停止する
    python3 create_pattern.py --limit N       # 新規+再処理対象の処理行数を N に限定（hash-skip 行は制限外）
    python3 create_pattern.py --path-like PAT # 対象を path LIKE PAT で絞る（例 '%bubbletea%'）
    python3 create_pattern.py --dry-run       # 判定結果を表示し、wiki/DB を変更しない
    python3 create_pattern.py --db FILE       # DB パス
    python3 create_pattern.py --wiki-dir DIR  # wiki ディレクトリ
    python3 create_pattern.py --adapter NAME  # openai_compatible | opencode_cli（既定 config.toml [llm]）
    python3 create_pattern.py --base-url URL  # openai_compatible のみ（既定 config.toml [llm]）
    python3 create_pattern.py --model MODEL   # 既定 config.toml [llm] → アダプタ既定
    python3 create_pattern.py --max-chars N   # 本文の切り詰め上限（既定 0 = 無制限。全文読む）
    python3 create_pattern.py --timeout SEC   # リクエストタイムアウト（既定 120）

前提: index_markdown.py を先に実行し、documents に ingest_status 列と索引が最新であること。
1件ごとに [i/total] decision パス を出力し、完了時に集計を出力する。
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbase  # noqa: E402

# LLM の生成設定（スクリプト側の設定。接続設定は config.toml [llm] と adapters/openai_compatible.py の既定値）
LLM_BODY = {
    "reasoning_effort": "none",
    "reasoning_budget_tokens": 3072,
    "temperature": 0.5,
    "top_p": 0.95,
}

PROMPT_TEMPLATE = """あなたは知識ベースの Ingest エージェントです。以下のMarkdownファイルを読み、
将来の作業で再利用できる失敗・知見・手順を含むかを判定し、Wiki の Pattern ページへの変換を提案してください。

既存の Pattern ページ一覧:
{patterns}

判定基準:
- 再利用可能な失敗（症状・原因・対策が抽出できる）→ decision: "patterned"
- 再利用可能な知見・手順がある → decision: "patterned"
- 日次作業記録・一時的なメモなど再利用価値がない → decision: "not_needed"

出力は JSON のみにしてください。形式:
{{"decision": "patterned"|"not_needed", "patterns": [{{"pattern": "<既存ページ名 または 新規ページ名>", "dir": "<領域ディレクトリ（例: go/bubbletea）>", "type": "incident|decision|experiment", "section": "<Wikiへ追記するセクション本文（Markdown。結論・症状・原因・対策・再発防止を含める）>", "keywords": ["<検索語>", ...]}}, ...]}}

制約:
- decision が not_needed の場合、patterns は空配列 [] にしてください
- decision が patterned の場合、patterns に 1 件以上含めてください。ファイル内に独立した失敗・知見・手順が複数ある場合は、1 知見 = 1 エントリに分けてください（同一テーマにまとめるべき内容は分けない）
- 新規ページ名は小文字英数と _ で、incident_* / decision_* / experiment_* のいずれかにしてください
- dir は既存 Pattern 一覧の領域階層（技術/プロジェクト。例: go/bubbletea）から選ぶ。該当領域が無い場合は ""（wiki 直下）。パターン種別（incident 等）は dir に含めない
- 原文にない情報を追加しないでください
- section 内にファイルパスや provenance を書かないこと（スクリプトが自動付記します）

ファイルパス: {path}

ファイル内容:
{content}
"""


def parse_output(text):
    """LLM 出力から JSON を抽出し (dict, None) を返す。失敗時は (None, error)。"""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t.strip())
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None, "no json object"
    try:
        obj = json.loads(t[start:end + 1])
    except json.JSONDecodeError as exc:
        return None, f"json: {exc}"
    if obj.get("decision") not in ("patterned", "not_needed"):
        return None, f"bad decision: {obj.get('decision')!r}"
    if "patterns" not in obj and "pattern" in obj:
        # 旧形式（単一 pattern）の後方互換: patterns 配列に正規化する
        obj["patterns"] = [{k: obj.get(k) for k in ("pattern", "dir", "type", "section", "keywords")}]
    if obj.get("decision") == "patterned":
        if not isinstance(obj.get("patterns"), list) or not obj["patterns"]:
            return None, "patterned but patterns empty"
    return obj, None


def valid_page_name(name):
    """ページ名を検証し '<stem>.md' を返す。不正なら None。"""
    stem = name[:-3] if name.endswith(".md") else name
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", stem):
        return None
    return stem + ".md"


def valid_dir(d):
    """領域ディレクトリを検証して返す。空・不正は ''（wiki 直下）にフォールバック。"""
    d = (d or "").strip().strip("/")
    if not d:
        return ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*){0,2}", d):
        return ""
    return d


def write_pattern(wiki_dir, page_dir, page_name, raw_path, section, ts):
    """patterned の書き込み: 既存ページへ追記 or 新規作成（領域ディレクトリ作成可）。provenance を自動付記する。"""
    page_path = os.path.join(wiki_dir, page_dir, page_name)
    if os.path.exists(page_path):
        with open(page_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n## Ingest {ts}（Raw: {os.path.basename(raw_path)}）\n\n"
                    f"{section}\n\n- 根拠: Raw `{raw_path}`（ingest: {ts}）\n")
    else:
        stem = page_name[:-3]
        os.makedirs(os.path.dirname(page_path), exist_ok=True)
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(f"# {stem}\n\n{section}\n\n## 根拠\n- Raw: `{raw_path}`（ingest: {ts}）\n")
    return page_path


def append_log(wiki_dir, raw_path, page_name, ts, created, reingest):
    """wiki/log.md に Ingest 記録を追記する。reingest は更新ファイルの再Ingest。"""
    log_path = os.path.join(wiki_dir, "log.md")
    action = "新規作成" if created else "セクション追記"
    if reingest:
        action = f"再Ingest（ファイル更新）→ {action}"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Ingest（{page_name}）\n\n"
                f"- 理由: create_pattern.py による自動 Ingest\n"
                f"- Raw: `{raw_path}`（ingest_status='patterned'）\n"
                f"- 変更: `{page_name}` へ{action}\n")


def process_row(i, total, p, reingest, current_hash, args, pattern_names, ts, adapter):
    """1件分: 読み込み → LLM 判定 → wiki 書き込み → DB 更新（commit）。(kind, i, p, detail, ms) を返す。

    reingest: 元の ingest_status が patterned / not_needed（更新ファイルの再Ingest）。
    current_hash: 現ファイルの hash。成功時に ingested_hash として保存する。
    """
    t0 = time.perf_counter()
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as exc:
        return ("error", i, p, str(exc), 0)

    if args.max_chars and len(content) > args.max_chars:
        content = content[:args.max_chars]

    prompt = PROMPT_TEMPLATE.format(
        patterns="\n".join(pattern_names) if pattern_names else "（なし）",
        path=p,
        content=content,
    )

    def mark_error(msg):
        """失敗フラグ保存: 新規行は ingest_status='error'。再Ingest 行は元の status を保ち
        ingested_at / ingested_hash を進めて、内容（hash）が変わるまで再試行しない。"""
        if args.dry_run:
            return
        con = sqlite3.connect(args.db)
        if reingest:
            con.execute(
                "UPDATE documents SET ingested_at = ?, ingested_hash = ?, ingest_error = ? WHERE path = ?",
                (int(time.time()), current_hash, msg[:500], p),
            )
        else:
            con.execute(
                "UPDATE documents SET ingest_status = 'error', ingested_at = ?, ingested_hash = ?, "
                "ingest_error = ? WHERE path = ?",
                (int(time.time()), current_hash, msg[:500], p),
            )
        con.commit()
        con.close()

    text, err = adapter.chat(prompt)
    if err:
        mark_error(err)
        return ("error", i, p, err, 0)

    obj, parse_err = parse_output(text)
    if parse_err:
        err = f"parse: {parse_err}"
        mark_error(err)
        return ("error", i, p, err, 0)

    decision = obj["decision"]
    epoch = int(time.time())

    if args.dry_run:
        if decision == "patterned":
            decision = f"patterned x{len(obj.get('patterns') or [])}"
        return ("dry", i, p, decision, int((time.perf_counter() - t0) * 1000))

    if decision == "not_needed":
        con = sqlite3.connect(args.db)
        con.execute(
            "UPDATE documents SET ingest_status = 'not_needed', ingested_at = ?, ingested_hash = ?, "
            "ingest_error = '' WHERE path = ?",
            (epoch, current_hash, p),
        )
        con.commit()
        con.close()
        tag = "（再評価）" if reingest else None
        return ("not_needed", i, p, tag, int((time.perf_counter() - t0) * 1000))

    # patterned: patterns 配列の各エントリを個別のページへ書き込む（同一ページならセクション追記）
    valid = []
    skipped = []
    for e in obj.get("patterns") or []:
        if not isinstance(e, dict):
            skipped.append(f"not object: {e!r}")
            continue
        page_name = valid_page_name(e.get("pattern") or "")
        if not page_name:
            skipped.append(f"bad page name: {e.get('pattern')!r}")
            continue
        section = (e.get("section") or "").strip()
        if not section:
            skipped.append(f"empty section: {page_name}")
            continue
        valid.append((page_name, valid_dir(e.get("dir")), section))
    if not valid:
        err = "; ".join(skipped) or "patterned but no valid patterns"
        mark_error(err)
        return ("error", i, p, err, 0)

    actions = []
    for page_name, page_dir, section in valid:
        created = not os.path.exists(os.path.join(args.wiki_dir, page_dir, page_name))
        write_pattern(args.wiki_dir, page_dir, page_name, p, section, ts)
        append_log(args.wiki_dir, p, page_name, ts, created, reingest)
        actions.append(os.path.join(page_dir, page_name))
    action = f"patterned x{len(valid)} -> {', '.join(actions)}"
    if skipped:
        action += f"（スキップ {len(skipped)}: {'; '.join(skipped)}）"
    if reingest:
        action = f"再Ingest {action}"

    con = sqlite3.connect(args.db)
    con.execute(
        "UPDATE documents SET ingest_status = 'patterned', ingested_at = ?, ingested_hash = ?, "
        "ingest_error = '' WHERE path = ?",
        (epoch, current_hash, p),
    )
    con.commit()
    con.close()
    return ("patterned", i, p, action, int((time.perf_counter() - t0) * 1000))


def main():
    parser = argparse.ArgumentParser(description="documents 未確認ファイルから Wiki Pattern を生成する")
    parser.add_argument("--db", default=kbase.DB_DEFAULT, help="DB パス")
    parser.add_argument("--wiki-dir", default=kbase.WIKI_DEFAULT, help="wiki ディレクトリ")
    parser.add_argument("--adapter", default=None,
                        choices=["openai_compatible", "opencode_cli"],
                        help="LLM 接続アダプタ（既定 config.toml [llm]）")
    parser.add_argument("--base-url", default=None,
                        help="openai_compatible のベースURL（既定 config.toml [llm]）")
    parser.add_argument("--model", default=None, help="モデル名（既定 config.toml [llm] → アダプタ既定）")
    parser.add_argument("--limit", type=int, default=0, help="処理する未確認行数（既定 0 = 無制限）")
    parser.add_argument("--path-like", default="", help="対象を path LIKE で絞る（空は全未確認）")
    parser.add_argument("--max-chars", type=int, default=0, help="本文の切り詰め上限（0 は無制限）")
    parser.add_argument("--timeout", type=int, default=None,
                        help="リクエストタイムアウト秒（既定 config.toml [llm] → 120）")
    parser.add_argument("--dry-run", action="store_true", help="判定表示のみ（wiki/DB 変更なし）")
    args = parser.parse_args()

    adapter = kbase.create_llm_adapter(args.adapter, args.base_url, args.model,
                                       args.timeout, body=LLM_BODY)

    con = sqlite3.connect(args.db)
    cols = {row[1] for row in con.execute("PRAGMA table_info(documents)")}
    if "ingest_status" not in cols or "ingested_hash" not in cols or "ingest_priority" not in cols:
        con.close()
        print("error: documents に ingest_status / ingested_hash / ingest_priority 列がありません。先に index_markdown.py を実行してください")
        return
    con.execute(kbase.IGNORE_SCHEMA)
    kbase.ensure_error_columns(con)
    files, dirs = kbase.load_ignore(con)

    wiki_prefix = args.wiki_dir if args.wiki_dir.endswith(os.sep) else args.wiki_dir + os.sep
    pattern_names = [os.path.relpath(r[0], args.wiki_dir) for r in con.execute(
        "SELECT path FROM documents WHERE path LIKE ? ORDER BY path", (wiki_prefix + "%",)
    )]

    query = ("SELECT path, ingest_status, modified_at, ingested_at, ingested_hash, hash, ingest_priority FROM documents "
             "WHERE (ingest_status = '' "
             "OR (ingest_status IN ('patterned', 'not_needed') AND modified_at > ingested_at) "
             "OR (ingest_status = 'error' AND ingested_hash <> hash))")
    params = ()
    if args.path_like:
        query += " AND path LIKE ?"
        params = (args.path_like,)
    query += (" ORDER BY (ingest_status = '') DESC, COALESCE(ingest_priority, -1) DESC, modified_at ASC")
    candidates = [row for row in con.execute(query, params).fetchall()
                  if not kbase.is_ignored(row[0], files, dirs) and not row[0].startswith(wiki_prefix)]

    # 更新候補（patterned / not_needed）を hash 比較で分離:
    # 一致 = 偽更新（touch 等）→ LLM 不要、ingested_at のみ更新。相違 = 再Ingest 対象
    hash_skip = [r for r in candidates
                 if r[1] in ("patterned", "not_needed") and r[4] and r[4] == r[5]]
    rows = [r for r in candidates if r not in hash_skip]
    if args.limit:
        rows = rows[:args.limit]
    new = sum(1 for r in rows if r[1] == "")
    updated = sum(1 for r in rows if r[1] in ("patterned", "not_needed"))
    error_retry = sum(1 for r in rows if r[1] == "error")
    unscored = sum(1 for r in rows if r[6] is None)

    if hash_skip and not args.dry_run:
        con.executemany("UPDATE documents SET ingested_at = ? WHERE path = ?",
                        [(r[2], r[0]) for r in hash_skip])
        con.commit()
    con.close()

    print(f"targets: {len(rows)}（新規: {new} / 更新: {updated} / error再試行: {error_retry}）")
    print(f"priority 未採点: {unscored}")
    print(f"hash-skip: {len(hash_skip)}")
    print(f"patterns: {len(pattern_names)}")
    if not rows:
        return

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    total = len(rows)
    counts = {"patterned": 0, "not_needed": 0, "dry": 0, "errors": 0}
    sum_ms = 0
    started = time.perf_counter()
    stop_requested = kbase.setup_stop_key()
    print("キー入力: q で処理中のファイルを完了後、停止")
    for i, (p, status, _mod, _ing, _ih, h, pr) in enumerate(rows, 1):
        if stop_requested():
            print(f"stop: {i - 1}/{total} 件で停止（残りは未処理）")
            break
        reingest = status in ("patterned", "not_needed")
        kind, i, p, detail, elapsed_ms = process_row(i, total, p, reingest, h, args, pattern_names, ts, adapter)
        if kind == "error":
            counts["errors"] += 1
            print(f"[{i}/{total}] error: {p}: {detail}")
        else:
            counts[kind] += 1
            sum_ms += elapsed_ms
            suffix = f"  priority={pr}" + (f" {detail}" if detail else "")
            print(f"[{i}/{total}] {kind}{suffix}  {elapsed_ms} ms  {p}")

    total_seconds = time.perf_counter() - started
    done = counts["patterned"] + counts["not_needed"] + counts["dry"]
    print(f"patterned: {counts['patterned']}")
    print(f"not_needed: {counts['not_needed']}")
    if counts["dry"]:
        print(f"dry: {counts['dry']}")
    print(f"errors: {counts['errors']}")
    print(f"average: {sum_ms / done:.0f} ms" if done else "average: -")
    print(f"total: {total_seconds:.1f} s")


if __name__ == "__main__":
    main()
