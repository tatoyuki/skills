# ingest-flags.md

## フラグの意味（documents.ingest_status）

| 値         | 意味                                  |
| ---------- | ------------------------------------- |
| ''         | 未確認（Ingest の内容確認がまだ）     |
| patterned  | 内容確認済み。Wiki Pattern に反映した |
| not_needed | 内容確認済み。pattern 化不要だった    |
| error      | 直近の Ingest が LLM 失敗（ingest_error にメッセージ）。内容（hash）が変わるまで再試行しない |

## 状態機械

```text
''（未確認）──Ingest 判定──> patterned
                └──────────> not_needed
                └──────────> error（LLM 失敗）──hash 変更──> 再Ingest 対象
```

- リセット（再確認させる）: `UPDATE documents SET ingest_status='', ingested_at=0 WHERE path=?`
- 設定: `UPDATE documents SET ingest_status='patterned'|'not_needed', ingested_at=<epoch 秒> WHERE path=?`
- 失敗時（create_pattern.py）: 新規行は `ingest_status='error'` + `ingest_error`。再Ingest 行は元の status を保ち ingested_at / ingested_hash を進める（modified_at > ingested_at が偽になり再選出されない）

## sync 時の挙動

- 既存 path の UPDATE は modified_at / hash のみ。**フラグは保持される**（touch しても patterned のまま）
- 行の DELETE（ファイル削除）でフラグも失われる。再追加されると '' で復活
- 同名移動では find_reusable がフラグを引き継ぐ（move-detection.md 参照）
- ignore_path に追加された行は sync で更新・削除されないためフラグが残る

## 未決の課題

**patterned のファイルが内容変更されたら pattern を再作成するか？**

- 現状設計: 再作成しない。modified_at / hash だけ更新され patterned が残る
- 論点: pattern 化後の加筆（新しい失敗・知見）が Wiki に反映されない vs 再作成のプロンプトコストと既存 pattern の劣化リスク
- 記録: task.md「課題 ファイル更新時パターン再作成するか？」

## 検索例

```sql
-- 未確認の一覧（候補絞り込み。内容判定は本文全体を読む）
SELECT path, summary FROM documents WHERE ingest_status='' ORDER BY modified_at DESC;
-- 特定プロジェクトの確認済み/未確認
SELECT ingest_status, COUNT(*) FROM documents WHERE path LIKE '%bubbletea%' GROUP BY ingest_status;
```
