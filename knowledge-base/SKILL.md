---
name: knowledge-base
description: "ローカルMarkdown知識ベースの検索、索引管理、Pattern作成、Wiki運用に使用する。"
---

# knowledge-base

ローカル Markdown 知識ベースを検索・整理・保守するための Skill。

Markdown を正本とし、`index.db` は検索用の派生インデックスとして扱う。

目的は、過去の経験を再利用可能な知識として残し、同じ調査・設計ミス・失敗を繰り返さないこと。

## 何をしたいときにどのファイルを読むか

### 検索・索引

- 関連文書を探す: `query.md`
- Markdown を `index.db` に同期する: `bin/index_markdown.py`（`hash` 列で移動検知し、同名同一内容のファイルは要約と Ingest フラグ `ingest_status` を再利用する）
- summary を生成・更新する: `bin/generate_summary.py`
- 未確認ファイルから Pattern を一括生成する: `bin/create_pattern.py`（`--limit N` で見る行数。詳細は `ingest.md` の「一括 Ingest」）

### Pattern

- 再利用可能な知見を作成・更新する: `ingest.md`
- 記述形式: `template/` 配下のテンプレートに従う
  - 設計判断: `template/decision_pattern.md`
  - 障害・調査: `template/incident_pattern.md`
  - 比較・検証: `template/experiment_pattern.md`

### Wiki

- Raw から知識を取り込む: `ingest.md`
- Wiki を参照する: `query.md`
- Wiki の品質を検査する: `lint.md`

## 共通原則

- Markdown を正本とする
- `index.db` は検索・管理用の派生データとする
- `summary` は検索補助であり、事実の根拠にはしない
- Raw は事実・観測・一次情報を保持する
- Wiki Pattern は再利用可能な知識として扱う
- 推測、評価、実測を区別する
- provenance は Markdown から追跡できるようにする
- 存在しないファイル、パス、根拠を書かない
- 過去の判断を無条件に踏襲せず、現在の条件と比較する
- DB スキーマ変更はユーザー承認なしに行わない

## 設定

環境依存の設定は `config.toml` に記述する。`config.toml` は個人環境の実値を含むためリポジトリには含めない。初回は `config.toml.template` をコピーして作成する。

必須:

- `knowledge_root`: Knowledge Base のルートディレクトリ

LLM 接続（`[llm]` セクション。generate_summary.py / create_pattern.py が使用）:

- `adapter`: `openai_compatible`（OpenAI 互換 API 直呼び）| `opencode_cli`（opencode run 経由）
- `base_url` / `model` / `timeout`: 接続パラメータ。未設定はアダプタ既定値
- 優先順位: CLI オプション（`--adapter` 等）> config.toml > アダプタ既定値
- 設定の読み込みは `bin/kbase.py`（3スクリプト共通）

Knowledge Base は次の構造を前提とする。

```text
<knowledge_root>/
├── index.db
├── raw/
└── wiki/
```
