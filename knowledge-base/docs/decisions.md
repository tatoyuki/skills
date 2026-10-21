# decisions.md

設計決定の記録（ADR 形式）。取り消し・変更時は本文を更新する。

## D1: Raw は doc/knowledge/raw/ 一本（2026-10-12）

- 状態: 採用
- 決定: 自己反省レポート等の一次資料は `doc/knowledge/raw/` にのみ置く。`report/` ディレクトリは作らない
- 理由: 分散していた `doc/knowledge/report/` への参照は死参照になっていた（AGENTS.md・index.db 旧行で実測）。一箇所に統一し provenance のパス規則を単純にする

## D2: wiki/ 配下自体は pattern 化しない（2026-10-12）

- 状態: 採用
- 決定: create_pattern.py は documents の wiki/ 配下の行をスキップする
- 理由: Pattern を Pattern の材料にすると循環し、Wiki が自己増殖する

## D3: Markdown インデント対策はスクリプトにしない（2026-10-12）

- 状態: 採用
- 決定: 整形スクリプト（恒久ツール）は作らない。原因（アーカイブの誤書式の模倣）を除去し、AGENTS.md の規則を「見出し直下の本文・第一級列表項も0列」へ拡張して潰す
- 理由: ユーザー方針「検出・修復メカニズムの追加ではなく、原因を深掘りして潰す」。詳細: doc/knowledge/raw/2026-10-12-task-md-indent-error-2.md

## D4: summary は query（検索）専用（2026-10-12）

- 状態: 採用
- 決定: summary は検索の候補絞り込みのみに使う。Ingest の内容確認は本文全体を読んで行う。create_pattern.py は既定で本文全体を LLM に渡す
- 理由: 要約に基づく判定は情報欠落による誤判定を生む

## D5: Pattern ページはサブディレクトリを作らない（2026-10-10）
- 状態: D9 にて一部改訂（「サブディレクトリ不作成」を廃止）。命名則も D10 にて改訂（`pattern_` 除去）
- 決定: wiki/ は Pattern ページのフラット配置（命名則 `incident_pattern_*.md` 等）。カテゴリは index.db（documents.path と summary）が持つ
- 理由: 構造は索引（index.db）が担い、パス規則を単純に保つ

## D6: task.md の frontmatter は archive のみ（2026-10-12）

- 状態: 採用
- 決定: task-md ワークフローが処理する frontmatter は `archive:` のみ。`spec:` は不要（死参照となっていたため削除）
- 理由: 仕様内容はプロジェクト設計文書と knowledge-base docs/ が担う。task.md は作業状態の記録に責務を限定する

## D7: wiki/index.md を廃止し役割を index.db に移す（2026-10-12）

- 状態: 採用
- 決定: `wiki/index.md` を削除する。ページ一覧・一言説明は documents（`path LIKE '%/wiki/%'` の summary）が担い、件数は provenance から導出、P## ID は廃止してページ名で参照する
- 理由: 二重の正本による同期乖離（2026-10-12 の index.md 重複行バグが実証）。create_pattern.py の簡素化
- 影響: 既存文書中の P## 参照（wiki P12 等）は歴史記録として残置。以後の参照はページ名

## D8: wiki/overview.md を廃止（2026-10-12）

- 状態: 採用
- 決定: `wiki/overview.md` を削除する。構造は docs/architecture.md、規則は ingest.md / decisions.md / query.md、操作は SKILL.md / lint.md が担う
- 理由: wiki 内のメタ文書がスキル側文書と重複し、既に陳腐化していた（`raw/self_review.db` を依然記載、検索順が乖離）。D7 と同じ二重の正本の問題

## D9: Pattern の領域ディレクトリを許可（2026-10-12）

- 状態: 採用（D5 の「サブディレクトリ不作成」を改訂）
- 決定: `wiki/` 直下または領域ディレクトリ（技術/プロジェクト階層。例: `go/bubbletea/`。小文字英数と `_` `-`、最大3階層）に Pattern を置く。パターン種別カテゴリディレクトリは作らない（種別はファイル名プレフィックス）。`log.md` は wiki 直下1本のまま
- 理由: Pattern 数増加に伴い一覧性・ドメイン局所化が必要。index.db 検索・find_reusable（同名ベース）はサブディレクトリ対応済みで移行コストが低い
- 実装: create_pattern.py の JSON 契約に `dir` 追加（不正値は直下フォールバック）、already_ingested の再帰化、write_pattern の makedirs

## D10: Pattern 命名則から `pattern_` を除去（2026-10-12）

- 状態: 採用（D5 の命名則を改訂）
- 決定: Pattern ページ名は `<type>_<slug>.md`（incident_ / decision_ / experiment_）。従来則 `incident_pattern_*.md` 等の `pattern_` を除去する
- 理由: 種別プレフィックスだけで Pattern と識別でき、`pattern_` は冗長でファイル名を長くしている（例: incident_pattern_deadlock_semaphore_event_loop.md）
- 実装: create_pattern.py の PROMPT 制約を `incident_* / decision_* / experiment_*` に変更（コード検証は不変）。既存 16 ページは mv で移行（mv → sync → 本文編集 → sync の順、move-detection.md 教訓参照）

## D11: スキル名を knowledge-base に変更（2026-10-12）

- 状態: 採用（ユーザー指示。task.md「スキル名変更」）
- 決定: スキル `knowledge-index` を `knowledge-base` に改名する（ディレクトリ `doc/llm/skills/knowledge-base/`）
- 理由: スキルは知識ベース全体の運用（検索・索引・Ingest・Wiki 運用）を担っており、「index」より「base」が実態に合う
- 実装: ディレクトリ mv → sync（同名移動で summary 継承: reused 14）→ 参照更新（SKILL.md / ingest.md / lint.md / docs/ / bin/index_markdown.py docstring / bin/knowledge.sh / CONTEXT.md / wiki 現在参照3箇所）→ sync → generate_summary.py。歴史記録（wiki/log.md、task_archive.md、incident_rename_stale_references.md の事例本文）は旧名のまま残置

## 未決: ファイル更新時に pattern を再作成するか

- 状態: 未決（task.md「課題」セクション）
- 現状: 再作成しない。patterned フラグは内容変更でも残る
- 論点: 加筆の未反映 vs 再生成コストと既存 pattern 劣化リスク
