# architecture.md

## 知識の構造

```text
knowledge/
├── index.db
├── raw/
└── wiki/
    ├── log.md
    ├── *.md（Pattern。領域の無いものは直下）
    └── <領域dir>/*.md（例: go/bubbletea/。技術/プロジェクト階層、最大3階層）
```

## wiki/log.md の役割

Wiki 変更理由の追記型記録。Pattern がなぜ変更されたかを後から追跡できるようにする。

- 意味のある Wiki 変更時に追記する（ingest.md 手順9）。create_pattern.py による自動 Ingest でも追記される
- エントリは削除・書き換えしない。訂正は新しいエントリの追記で行う
- エントリ形式:

```text
## YYYY-MM-DD HH:MM:SS — 操作（対象）

- 理由: <変更の理由>
- Raw: `<raw の実パス>`（Ingest の場合）
- 変更: <新規作成 / セクション追記 / 削除 等>
```

## スキルの構造

```text
knowledge-base/
├── SKILL.md（入口。操作の索引）
├── ingest.md / query.md / lint.md（運用手順書）
├── config.toml（knowledge_root の設定）
├── template/（decision_pattern.md / incident_pattern.md / experiment_pattern.md）
├── bin/（index_markdown.py / generate_summary.py / create_pattern.py）
└── docs/（設計文書。本ディレクトリ）
```

## データフロー概要

```text
実ファイル ─index_markdown.py→ documents（index.db）
documents ─generate_summary.py→ summary（検索用）
documents ─create_pattern.py→ wiki/ Pattern + ingest_status フラグ
```

## 設計文書

一覧と書くルールは [README.md](README.md)（一覧は README に1箇所だけ置く）。
