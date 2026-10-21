# dependencies.md

実行時依存の一覧（2026-10-12 実測）。

## 言語・標準ライブラリ

| 依存                       | 用途                                                                 |
| -------------------------- | -------------------------------------------------------------------- |
| python3（実測 3.14.4）    | 3スクリプト（index_markdown / generate_summary / create_pattern）    |
| 標準ライブラリのみ         | argparse / os / re / json / sqlite3 / subprocess / time / urllib     |
| sqlite3 モジュール（3.46.1）| index.db 読み書き。sqlite3 CLI は不要（本環境に存在しない。DB 操作は Python 経由） |

## 外部コマンド

| コマンド | 用途                                                                 | 欠如時の挙動                                     |
| -------- | -------------------------------------------------------------------- | ------------------------------------------------ |
| xxhsum   | index_markdown.py の hash 計算（`xxhsum --filelist` 一括）           | 空 dict にフォールバック（ハッシュなし従来動作）。移動検知（move-detection.md）は効かなくなる |

## LLM API（generate_summary.py / create_pattern.py）

- OpenAI 互換 `/v1/chat/completions` を直接呼ぶ。既定 BASE_URL `http://127.0.0.1:8080/v1`（ローカルサーバ）。流儀は [llm-usage.md](llm-usage.md)
- Sleev → Strata への中継はヘッダで指定（`sleev-harness: opencode`、`sleev-base-url: http://127.0.0.1:8080/v1`）。環境依存の実値は `config.toml` `[llm.headers]` に記述し、アダプタ既定ヘッダは Content-Type のみ
- スクリプト既定値（BASE_URL・model・BODY）は `~/.config/opencode/opencode.jsonc` の strata-sleev 設定に基づく。環境依存の model 名は文書に書かない（README ルール）

## ファイル

| ファイル            | 用途                                                       |
| ------------------- | ---------------------------------------------------------- |
| `config.toml`       | `knowledge_root` の設定（SKILL.md 設定セクション）         |
| `index.db`          | 検索用派生インデックス。スキーマはスクリプトが自動作成・移行（[data-model.md](data-model.md)） |
| `wiki/log.md`       | Wiki 変更理由の追記型記録（[architecture.md](architecture.md)） |
