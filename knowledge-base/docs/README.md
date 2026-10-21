# knowledge-base docs/

knowledge-base スキルの設計文書ディレクトリ。運用手順（SKILL.md / ingest.md / query.md / lint.md）はスキル直下にあり、本ディレクトリは「なぜその形か」（構造・データモデル・決定）を担う。

## 文書一覧

| 文書                                   | 内容                                 |
| -------------------------------------- | ------------------------------------ |
| [architecture.md](architecture.md)     | 知識・スキルの構造とデータフロー概要 |
| [data-model.md](data-model.md)         | index.db スキーマと移行履歴          |
| [pipeline.md](pipeline.md)             | 3段パイプライン、冪等性、並列制約    |
| [move-detection.md](move-detection.md) | ファイル移動検知の仕組みと限界       |
| [ingest-flags.md](ingest-flags.md)     | ingest_status 状態機械と sync 挙動   |
| [llm-usage.md](llm-usage.md)           | LLM 呼び出しの流儀と JSON 契約       |
| [dependencies.md](dependencies.md)     | 実行時依存（python / xxhsum / API）  |
| [decisions.md](decisions.md)           | 設計決定記録（ADR）                  |

## 書くルール

- 設計・データモデル・決定は本ディレクトリ。運用手順はスキル直下
- 事実はスクリプト・実 DB の実測に基づいて書く（model 名など実行環境に依存する値は書かない）
- 設計上の決定は個別文書に散らさず decisions.md に追記する
- 文書を増やしたら本一覧に追加する（一覧はここ1箇所。他文書に重複一覧を作らない）
