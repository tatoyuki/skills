#!/usr/bin/env python3
"""index_markdown.py — home 配下の全 Markdown ファイルを documents テーブルへ登録する。

knowledge-base スキル用。ファイルの登録のみを行い、summary（要約）は空文字のまま入れる。
要約生成は task.md の「要約生成プロンプト」を使う別工程で行う。

2026-10-10 仕様変更:
- documents に created_at（作成日時）カラムは持たない
- modified_at（更新日時）はエポック秒の INTEGER で保持する
- 2回目以降の実行は既存行を更新する（INSERT OR IGNORE は廃止）
- 走査結果に無い path（ファイルが削除された行）は削除する
- documents は summary_at（要約生成日時。エポック秒。既定 0）を持つ
- ignore_path テーブルの指定を除外条件として扱う（ファイルエントリは完全一致、
  ディレクトリエントリは配下すべて。ignore_path 該当の既存行は削除しない）

2026-10-12 仕様追加（ファイル移動検知）:
- documents は hash（xxhsum の XXH64。16hex 文字列。既定 ''）を持つ
- 各走査ファイルのハッシュは xxhsum --filelist でバッチ1回計算する
- 新規 path の INSERT 時に「hash 一致 かつ ファイル名（basename）一致 かつ summary あり」の
  既存行があれば要約を再利用する（summary をコピーし summary_at = 新modified_at。集計に reused）
- 旧 path の行は従来どおり DELETE（要約はコピー済みで失われない）

2026-10-12 仕様追加（Ingest フラグ）:
- documents は ingest_status（Ingest 確認状態。既定 ''。''=内容未確認 / patterned=pattern化して
  wikiに入れた / not_needed=pattern化不要だった）と ingested_at（Ingest 設定日時。エポック秒。既定 0）を持つ
- 既存行の UPDATE は mtime/hash のみのため、ファイル編集で ingest_status は保持される
- 移動検知（find_reusable）で再利用時は ingest_status もコピーする（同名移動でフラグを引き継ぐ）

2026-10-12 仕様追加（summary 再生成スキップ）:
- documents は summary_hash（要約生成時の hash。既定 ''）を持つ。この列は generate_summary.py が設定する
- index_markdown.py は UPDATE で modified_at / hash のみ更新するため summary_hash は保持される（ファイル編集で失わない）
- ファイル消失（DELETE）でフラグも消える。再登録時は ''（許容仕様）

2026-10-12 仕様追加（再Ingest 判定 ingested_hash）:
- documents は ingested_hash（Ingest 時点の hash。既定 ''）を持つ。この列は create_pattern.py が設定する
- 列追加時（ensure_schema）に ingest_status <> '' の行へ ingested_hash = hash を backfill
  （移行時点で wiki 内容と現ファイルが一致している扱い。初回の再 Ingest 洪水を防ぐ）
- index_markdown.py は UPDATE で modified_at / hash のみのため ingested_hash は保持される（ファイル編集で ingested_hash と hash が乖離 → create_pattern.py の再Ingest 対象になる）
- 移動検知（find_reusable）の再利用 INSERT でも ingested_hash = hash を設定（移動後もスキップ判定が効く）

使い方:
    python3 index_markdown.py                 # 全 Markdown を登録（既存 path は mtime 差分を更新）
    python3 index_markdown.py --root DIR      # 探索ルート（既定: config.toml index_root。未設定ならホームディレクトリ）
    python3 index_markdown.py --db FILE       # DB パス（既定 config.toml knowledge_root/index.db）
    python3 index_markdown.py --dry-run       # 登録せず、件数とサンプルのみ表示

modified_at は os.stat の st_mtime（エポック秒）。
path には UNIQUE 制約があり、再実行（2回目以降）は既存行を重複登録するのではなく更新する:
  - 新規 path: INSERT
  - 既存 path で mtime が変わった行: UPDATE（summary は別工程で生成されるため更新しない）
  - mtime が同じ行: 何もしない
  - 走査結果に無い path（ファイルが削除された行）: DELETE
削除は走査した root 配下の行だけが対象（--root で部分ディレクトリを指定した場合、root 外の行は削除しない）。
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbase  # noqa: E402

ROOT_DEFAULT = kbase.INDEX_ROOT_DEFAULT

def ensure_schema(con):
    """documents を作成し、既存 DB に hash / summary_hash / ingest_status / ingested_at /
    ingested_hash / ingest_priority 列がなければ ALTER TABLE で追加する（移行）。"""
    con.execute(kbase.SCHEMA)
    cols = {row[1] for row in con.execute("PRAGMA table_info(documents)")}
    if "hash" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN hash TEXT NOT NULL DEFAULT ''")
    if "summary_hash" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN summary_hash TEXT NOT NULL DEFAULT ''")
    if "ingest_status" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN ingest_status TEXT NOT NULL DEFAULT ''")
    if "ingested_at" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN ingested_at INTEGER NOT NULL DEFAULT 0")
    if "ingested_hash" not in cols:
        con.execute("ALTER TABLE documents ADD COLUMN ingested_hash TEXT NOT NULL DEFAULT ''")
        # backfill: 既存 Ingest 済み行は移行時点の hash を ingest 時点 hash として扱う
        con.execute("UPDATE documents SET ingested_hash = hash WHERE ingest_status <> ''")
    if "ingest_priority" not in cols:
        # ingest_priority: ingest 候補の優先度 0〜3（generate_summary.py が採点）。NULL = 未採点
        con.execute("ALTER TABLE documents ADD COLUMN ingest_priority INTEGER")
    kbase.ensure_error_columns(con)  # summary_error / summary_error_hash / ingest_error


def find_reusable(con, p, h):
    """移動検知: hash 一致 かつ basename 一致 かつ summary あり の既存行 (summary, summary_at, ingest_status, ingest_priority) を返す。

    複数候補は summary_at 最新を1件採用。ingest_status / ingest_priority もコピー対象（移動で引き継ぐ）。
    """
    if not h:
        return None
    base = os.path.basename(p)
    esc = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return con.execute(
        "SELECT summary, summary_at, ingest_status, ingest_priority FROM documents "
        "WHERE hash = ? AND summary <> '' AND path <> ? AND path LIKE ? ESCAPE '\\' "
        "ORDER BY summary_at DESC LIMIT 1",
        (h, p, "%" + os.sep + esc),
    ).fetchone()


def parse_args():
    parser = argparse.ArgumentParser(description="Markdown ファイルを documents テーブルへ登録する")
    parser.add_argument("--root", default=ROOT_DEFAULT, help="探索ルート")
    parser.add_argument("--db", default=kbase.DB_DEFAULT, help="DB パス（既定 config.toml knowledge_root/index.db）")
    parser.add_argument("--dry-run", action="store_true", help="登録しない")
    return parser.parse_args()


def collect_markdown(root):
    """root 配下の .md ファイルをフルパスで列挙する（symlink は追跡しない）。

    順序は os.walk の走査順（sort しない）。
    """
    paths = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            if name.lower().endswith(".md"):
                paths.append(os.path.join(dirpath, name))
    return paths


def sync(con, root, paths, files, dirs, hashes):
    """documents を走査結果 paths に同期し、操作件数の dict を返す。

    INSERT / UPDATE / DELETE のみ。summary は既存値を保持する。
    ignore_path 該当の path は INSERT/UPDATE/DELETE すべてで対象外（既存行は削除しない）。
    新規 path は移動検知（find_reusable）で既存行の要約を再利用できる場合 INSERT 時にコピーする。
    既存 path は mtime または hash の差分で UPDATE（hash 列の移行後初回実行は here で backfill される）。
    """
    existing = {row[0]: (row[1], row[2])
                for row in con.execute("SELECT path, modified_at, hash FROM documents")}
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "deleted": 0, "ignored": 0, "reused": 0}

    for p in paths:
        if kbase.is_ignored(p, files, dirs):
            counts["ignored"] += 1
            continue
        modified_at = int(os.stat(p).st_mtime)
        h = hashes.get(p, "")
        if p not in existing:
            reuse = find_reusable(con, p, h)
            if reuse:
                # 移動検知: 内容同一（hash 一致）なので要約を再生成せず使い回す（ingest_status も引き継ぐ）
                # summary_hash / ingested_hash も現在の hash と一致するのでそのまま設定（再生成・再Ingest スキップ判定が移動後も効く）
                con.execute(
                    "INSERT INTO documents (path, modified_at, summary, summary_at, hash, summary_hash, ingest_status, ingested_hash, ingest_priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (p, modified_at, reuse[0], modified_at, h, h, reuse[2], h, reuse[3]),
                )
                counts["reused"] += 1
            else:
                con.execute(
                    "INSERT INTO documents (path, modified_at, summary, hash) VALUES (?, ?, '', ?)",
                    (p, modified_at, h),
                )
                counts["inserted"] += 1
        elif existing[p] != (modified_at, h):
            # summary は別工程（要約生成プロンプト）で埋めるため、ここでは更新しない
            con.execute(
                "UPDATE documents SET modified_at = ?, hash = ? WHERE path = ?",
                (modified_at, h, p),
            )
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    # 削除されたファイルのレコードを消す（走査した root 配下のみ）
    prefix = root if root.endswith(os.sep) else root + os.sep
    scanned = set(paths)
    for row in con.execute("SELECT path FROM documents"):
        p = row[0]
        # ignore_path 該当の既存行は削除しない（指示: すでに格納してあるものは削除しなくてよい）
        if p.startswith(prefix) and p not in scanned and not kbase.is_ignored(p, files, dirs):
            con.execute("DELETE FROM documents WHERE path = ?", (p,))
            counts["deleted"] += 1

    con.commit()
    return counts


def print_report(scanned, counts, total):
    print(f"scanned: {scanned}")
    for key in ("inserted", "updated", "unchanged", "deleted", "ignored", "reused"):
        print(f"{key}: {counts[key]}")
    print(f"documents rows: {total}")


def main():
    args = parse_args()
    paths = collect_markdown(args.root)
    if not paths:
        print(f"Markdown ファイルが見つかりません: {args.root}")
        return

    if args.dry_run:
        print(f"root: {args.root}")
        print(f"db:   {args.db}")
        print(f"files: {len(paths)}")
        for p in paths[:5]:
            print(f"  {p}")
        return

    con = sqlite3.connect(args.db)
    ensure_schema(con)
    con.execute(kbase.IGNORE_SCHEMA)
    files, dirs = kbase.load_ignore(con)
    hashes = kbase.hash_files(paths)
    counts = sync(con, args.root, paths, files, dirs, hashes)
    total = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    con.close()

    print_report(len(paths), counts, total)


if __name__ == "__main__":
    main()
