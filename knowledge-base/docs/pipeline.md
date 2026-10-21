# pipeline.md

## 3段パイプライン

```text
index_markdown.py  →  generate_summary.py  →  create_pattern.py
（索引同期）            （要約生成）             （Ingest / pattern 化）
```

```bash
python3 bin/index_markdown.py
python3 bin/generate_summary.py --limit N
python3 bin/create_pattern.py --limit N
```

## 各段の役割

### 1. index_markdown.py（sync）

- root 配下を走査し documents を実ファイルに一致させる
- 新規 path: INSERT。同名 + hash 一致で summary ありの旧行があれば summary / summary_at / ingest_status を引き継ぎ（移動検知。move-detection.md 参照）
- 既存 path: mtime・hash が違えば modified_at / hash のみ UPDATE（ingest_status は保持）
- 走査結果に無い path: DELETE（--root で部分指定した場合 root 外の行は削除しない）
- ignore_path 一致はスキップ

### 2. generate_summary.py（summary）

- `summary = ''` または `modified_at > summary_at` の行が対象。LLM で要約を生成し summary / summary_at / summary_hash を UPDATE
- LLM 出力は JSON `{"summary": "...", "priority": 0-3}` で、summary と同時に `ingest_priority`（Ingest 優先度、0〜3）も UPDATE する。判定は本文全体に基づく（priority は create_pattern.py の候補順に使用）。JSON パース失敗時は summary のみ保存し priority は NULL（再実行で再採点可）
- `--score-only`: 既存 summary だけから `ingest_priority` を採点する（対象 `summary <> '' AND ingest_priority IS NULL`）。1 バッチ `--batch N` 件（既定 20）を 1 回の LLM 呼び出しで処理し、summary は触らない
- 生成・採点の LLM 呼び出しは reasoning オフ（`reasoning_budget_tokens: 0`。ユーザー指示 2026-10-12）
- 生成時 hash（summary_hash）と現在の hash が一致する行は mtime 偽更新とみなし再生成しない（summary_at だけ更新、hash-skip として出力）。xxhsum 不在時は従来動作
- 失敗時（LLM エラー / パース失敗 / 空 summary）は summary_error / summary_error_hash に保存し、現 hash と一致する間は再試行しない（error-skip として出力）。成功時にクリア
- summary は query（検索）にのみ用いる。Ingest の内容確認には使わない
- `--limit N`（0 = 無制限）`--parallel N`（行単位なので並列可）`--max-chars`（既定 0 = 無制限。文字数でバイト数ではない）

### 3. create_pattern.py（Ingest）

- 対象: `ingest_status = ''`（新規）+ patterned / not_needed の行で `modified_at > ingested_at` かつ `hash <> ingested_hash`（更新ファイルの再Ingest。not_needed も再評価）+ error 行で `ingested_hash <> hash`（失敗後ファイルが変わったもののみ再試行）。`--path-like PAT` で絞り込み可
- 順序: 未確認（`ingest_status = ''`）優先 → `ingest_priority` 高い順（NULL は -1 扱いで最後）→ `modified_at` 古い順（`ORDER BY (ingest_status = '') DESC, COALESCE(ingest_priority, -1) DESC, modified_at ASC`）
- 更新候補のうち `hash = ingested_hash` の行は hash-skip（mtime 偽更新）: LLM を呼ばず ingested_at のみ UPDATE。`--limit` は新規+再処理対象のみにかかり hash-skip は制限外
- 本文全体を LLM に渡し JSON 判定（patterned / not_needed）。llm-usage.md 参照
- 失敗時（LLM エラー / パース失敗 / 不正ページ名）は ingest_error に保存。新規行は ingest_status='error'、再Ingest 行は元の status を保ち ingested_at / ingested_hash を進める（内容が変わるまで再試行しない）。成功時に ingest_error クリア
- patterned: wiki へ書き込み（既存ページ追記 or 新規 + provenance + log.md 追記。再Ingest は log.md に区別記録）→ ingest_status / ingested_at / ingested_hash を UPDATE
- not_needed: フラグ UPDATE のみ（wiki は触らない）
- wiki/ 配下自体と ignore_path 該当はスキップ

## 冪等性

- sync: 同一内容の再実行で変更なし（mtime・hash 一致なら untouched）
- summary: summary ありの行は再生成しない
- pattern: ingest_status 設定済みで hash = ingested_hash の行は再処理不要として対象外。provenance grep によるクラッシュ復帰は行わない（2026-10-12 決定。クラッシュ後再実行で生じた重複セクションは Lint が検出・削除）

## 並列とエラー処理

- generate_summary.py: 行単位 DB 更新のみなので `--parallel` 可
- create_pattern.py: wiki 共有ファイル（log.md / 同一 Pattern ページ）に触るため書き込みは直列固定
- LLM 応答の JSON パース失敗: error 計上しフラグは '' のまま（再実行で再試行可能）
- `--dry-run`: 判定結果を表示し wiki / DB を変更しない（レビュー経路）
