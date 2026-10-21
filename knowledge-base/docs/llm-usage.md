# llm-usage.md

## API

LLM 接続は `bin/adapters/` パッケージに切り出し済み（依存は標準ライブラリのみ）。
接続方式は `config.toml` の `[llm]` セクションで設定する（adapter / base_url / model / timeout / headers）。
CLI オプション `--adapter openai_compatible | opencode_cli` 等が config.toml より優先（既定は config.toml）。

| 設定（config.toml [llm]） | 値                            |
| ------------------------- | ----------------------------- |
| adapter                   | `openai_compatible`（既定）   |
| base_url                  | `http://127.0.0.1:8080/v1`    |
| timeout                   | 120 秒                        |

model は実行環境に依存するため config.toml でも既定は未設定（アダプタ既定）。`--model` で上書き可。
opencode_cli の model は provider/model 形式（既定 `strata-sleev/qwen3.8-flash-next-iq2_xs`）。
opencode run は呼び出しごとに新規セッションが1件作られる点に注意。

## generate_summary.py（要約）

- 入力: 本文を `--max-chars`（既定 8000。文字数でバイト数ではない）で切り詰め
- 生成設定: `max_tokens: 640`（暴走出力対策。実測で 1.3 万字 summary が発生し 1 件数分かかるケースがあった）
- 出力: 1行の summary → `UPDATE documents SET summary, summary_at, summary_hash`（hash 一致行は呼び出し自体スキップ。pipeline.md 参照）
- 失敗時: summary_error / summary_error_hash に保存（内容が変わるまで再試行しない）
- `--parallel N`: 行単位の独立処理なので並列可。ただし Strata エンジンは `--parallel 1`（1スロット）のため、エンジン側を上げない限り体感速度はほぼ変わらない

## create_pattern.py（Ingest 判定）

- 入力: **本文全体**（既定無制限。summary は判定に使わない）+ 既存 Pattern 一覧（documents の wiki/ 配下パス）
- 出力契約（JSON）:

```json
{"decision": "patterned|not_needed", "pattern": "<ページ名>", "dir": "<領域ディレクトリ（例: go/bubbletea。"" = wiki 直下）>", "type": "incident|decision|experiment", "section": "<追記セクション本文>", "keywords": ["..."]}
```

- パース失敗・decision 不正: error 計上 + 失敗フラグ（新規行は ingest_status='error'、ingest_error にメッセージ）。ファイル内容（hash）が変わるまで再試行しない
- ページ名は `[a-z0-9][a-z0-9_-]*` で検証。不正は error
- コンテキスト上限: llama サーバ ctx 131072。実測で 40 万字は通過、105 万字は HTTP 400（2026-10-12）。超過ファイルは失敗フラグで打ち切り（チャンク分割は未実装）

## 品質リスクとレビュー

- 品質は実行環境の model に依存する。判定・生成品質に誤りが含まれうる
- 緩和策:
    - `--dry-run` で書き込み前に判定をレビュー
    - provenance（根拠）から Raw 原文へ遡れる
    - 判定誤りは `UPDATE documents SET ingest_status='' WHERE path=...` + ページ削除で再実行可能
- 実測目安（2026-10-12、8件）: 1件 4〜24 秒。patterned 6 / not_needed 2 / errors 0
