# data-model.md

## index.db

knowledge base の索引層。テーブルは2つ。

### documents

| 列            | 型                                | 意味                                |
| ------------- | --------------------------------- | ----------------------------------- |
| id            | INTEGER PRIMARY KEY AUTOINCREMENT | 行 ID                               |
| path          | TEXT NOT NULL UNIQUE              | 絶対パス。provenance と同一文字列   |
| modified_at   | INTEGER NOT NULL                  | mtime（epoch 秒）                   |
| summary       | TEXT NOT NULL DEFAULT ''          | 要約。query（検索）にのみ用いる     |
| summary_at    | INTEGER NOT NULL DEFAULT 0        | 要約生成時刻（epoch 秒）            |
| hash          | TEXT NOT NULL DEFAULT ''          | xxh64（16文字 hex）。移動検知に使用 |
| summary_hash  | TEXT NOT NULL DEFAULT ''          | 要約生成時の hash。再生成スキップ判定に使用 |
| ingest_status | TEXT NOT NULL DEFAULT ''          | '' / patterned / not_needed / error |
| ingested_at   | INTEGER NOT NULL DEFAULT 0        | ingest 判定時刻（epoch 秒）         |
| ingested_hash | TEXT NOT NULL DEFAULT ''          | ingest 時点の hash。再Ingest 判定に使用 |
| ingest_priority | INTEGER                       | Ingest 優先度 0〜3（NULL = 未採点）。create_pattern.py の候補順に使用 |
| summary_error | TEXT NOT NULL DEFAULT ''          | 直近の要約生成失敗メッセージ（空 = 失敗なし） |
| summary_error_hash | TEXT NOT NULL DEFAULT ''     | 失敗時点の hash。現 hash と一致する間は再試行しない |
| ingest_error  | TEXT NOT NULL DEFAULT ''          | 直近の Ingest 失敗メッセージ（成功時にクリア） |

### ignore_path

| 列     | 型                                | 意味                           |
| ------ | --------------------------------- | ------------------------------ |
| id     | INTEGER PRIMARY KEY AUTOINCREMENT | 行 ID                          |
| path   | TEXT NOT NULL UNIQUE              | 除外パス                       |
| is_dir | INTEGER NOT NULL DEFAULT 0        | 1 = ディレクトリ配下すべて除外 |

ignore_path に一致する path は sync・summary 生成・pattern 生成のすべてでスキップされる。登録済みの行は削除されない。

## スキーマ移行

`SCHEMA` 定義と `ensure_schema()` の `ALTER TABLE` は対で書く（wiki P12: ALTER で入れた列が SCHEMA にないと新規 DB で失敗する）。

| 追加時期   | 列                             | 目的                                        |
| ---------- | ------------------------------ | ------------------------------------------- |
| 初期       | id, path, modified_at, summary | 索引                                        |
| 2026-10-12 | summary_at                     | 移動検知で summary_at 最新を1件採用するため |
| 2026-10-12 | hash                           | 移動検知（xxhsum --filelist で一括計算）    |
| 2026-10-12 | ingest_status, ingested_at     | Ingest フラグ                               |
| 2026-10-12 | ingested_hash                   | 更新ファイルの再Ingest 判定と偽更新スキップ（create_pattern.py）。列追加時に ingest_status <> '' へ ingested_hash = hash を backfill |
| 2026-10-12 | ingest_priority                 | Ingest 優先度（0〜3、NULL=未採点）。generate_summary.py が summary 生成と同一呼び出しで採点。既存 summary には `--score-only`。INTEGER のまま（TEXT 英単語案は ORDER BY が辞書順になるため却下） |
| 2026-10-12 | summary_error, summary_error_hash, ingest_error | LLM 失敗フラグ。失敗時にメッセージと失敗時点 hash を保存し、内容が変わるまで再試行しない（コンテキスト超過の無限リトライ防止）。kbase.ensure_error_columns() で移行 |

## provenance

Pattern ページの「根拠」セクションに記す Raw パスは documents.path と同一文字列である。Ingest 済み・再Ingest 要否の判定は DB の ingest_status / ingested_hash が権威（2026-10-12 改訂: provenance grep による冪等性判定は廃止。重複セクションは Lint で検出・削除）。
