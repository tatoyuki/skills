# Ingest — 知識を取り込む

Raw や現在の作業から、将来再利用できる知見を抽出し、Wiki Pattern として作成・更新する。

目的は作業履歴を保存することではない。

**未来の AI や開発者が、同じ調査・失敗・判断を繰り返さずに済む知識を残すこと**を目的とする。

Pattern の記述形式は `template/` 配下のテンプレートに従う。

---

# 基本原則

Ingest は次の知識循環を成立させるために行う。

```text
現在の作業・Raw
    ↓
再利用可能な知見を発見
    ↓
既存 Wiki Pattern を検索
    ↓
既存 Pattern を更新
または
新規 Pattern を作成
    ↓
provenance を記録
    ↓
index.db に登録・要約
    ↓
将来 Query で発見・再利用
```

- Raw は事実・観測・作業記録を保持する
- Wiki Pattern は将来再利用する知識を保持する
- Raw をそのまま Wiki にコピーしない
- `index.db` の summary は query（検索）にのみ用いる。Ingest の内容確認は本文全体を読んで行う（summary で判定しない）
- すべての Raw を Pattern にする必要はない。将来、同種の作業で調査・判断・実装を短縮できる知見だけを Pattern として残す
- 新しい Raw が来るたびに Pattern を新設しない
- まず既存 Pattern に統合できないか確認する
- 矛盾を見つけた場合は、勝手に整合させず Lint に渡す

---

# いつ Ingest するか

次のいずれかに該当し、将来の類似作業で調査・設計・判断を短縮できる知見が得られた場合に Ingest する。

## 1. 設計・判断

- 複数案を比較して設計方針を決定した
- 技術・ライブラリ・方式を選定した
- 既存方式を採用しなかった重要な理由がある
- 環境や要件による重要な制約が判明した
- 一見妥当に見える案に問題があると分かった
- 将来、同じ設計判断を再び行う可能性がある

Pattern 種別:

```text
decision-pattern
```

テンプレート:

```text
template/decision_pattern.md
```

## 2. 障害・調査

- 原因の分かりにくい不具合を解決した
- 環境依存の問題を調査した
- エラーメッセージだけでは原因を特定できなかった
- 複数の対処方法を試した
- 有効でない対処方法が判明した
- 再発時に調査を省略できる知見が得られた
- 原因と回避策の対応関係が分かった

Pattern 種別:

```text
incident-pattern
```

テンプレート:

```text
template/incident_pattern.md
```

## 3. 比較・検証

- 複数方式を実測比較した
- 性能、メモリ、VRAM、I/O などを測定した
- 技術選定のための検証を行った
- 仮説を実験によって確認または否定した
- 設定変更による効果を測定した
- 将来の判断に利用できる数値が得られた

Pattern 種別:

```text
experiment-pattern
```

テンプレート:

```text
template/experiment_pattern.md
```

---

# Ingest しないもの

次のような内容は、原則として Pattern にしない。

- 単純なタイポ修正
- 明白な小規模バグ修正
- Git 履歴だけで十分理解できる変更
- 一度しか使わない一時的な作業
- 単なるコマンド実行記録
- 途中経過だけの記録
- 結論や再利用可能な知見のない試行
- 既存 Pattern にすでに十分含まれている内容
- 一般的な公式ドキュメントを写しただけの内容
- 将来の判断を変えない情報

判断基準:

> 半年後、同種の問題に遭遇したとき、この Pattern を読むことで調査・設計・判断を短縮できるか。

---

# Pattern 種別の選択

```text
「なぜこの方式を選ぶべきか」
        ↓
decision-pattern

「なぜ壊れるのか、どう直すべきか」
        ↓
incident-pattern

「どちらが良いか、実際にどうだったか」
        ↓
experiment-pattern
```

複数に該当する場合は主目的で決める。

- 主目的が障害解決 → `incident-pattern`
- 主目的が性能比較 → `experiment-pattern`

無理に複数 Pattern へ分割しない。

---

# 既存 Pattern を先に確認する

新しい Pattern を作成する前に `query.md` を使用し、同じ知識を扱う Pattern が存在しないか確認する。

既存 Pattern がある場合は、新規作成より次を優先する。

- 新しい事例や根拠を追加する
- 適用範囲を更新する
- 新しい検証結果を反映する
- 古い結論を修正する

既存 Pattern と明確に異なる問題、条件、判断を扱う場合のみ、新しい Pattern を作成する。

意味が異なる、または対策が異なる場合は別 Pattern としてよい。

---

# Pattern に残すべき情報

Pattern 種別ごとの詳細な構造はテンプレートに従う。

種別を問わず、次を優先する。

1. 結論
2. 判断理由
3. 条件・制約
4. 重要な失敗
5. 実測・証拠
6. 適用範囲
7. 再検討条件
8. provenance

## 重要な失敗

将来、再度試してしまう可能性がある失敗は残す。

```text
Fyne は Linux 環境で日本語 IME 入力に問題があったため不採用。
```

単に「不採用」とだけ書かない。

## 事実・推測・判断を分ける

次を混同しない。

- 外部資料に記載された事実
- この環境で観測した事実
- 仮説・推測
- Wiki 側の判断

---

# 単発事例の扱い

Pattern は必ずしも複数事例から作る必要はない。

単発事例でも、

- 再発可能性が高い
- 調査コストが大きい
- 設計判断として重要
- 将来同じ失敗をする可能性が高い

場合は Pattern として残してよい。

ただし適用範囲を限定し、単発事例から過度に一般化しない。

複数の事例が蓄積した場合は Pattern を更新し、一般化の範囲を見直す。

---

# Raw の規則

- Raw は追記を基本とする
- 過去の事実や記録の意味を書き換えない
- 修正が必要なら新しい Raw または注記で補う
- Wiki Pattern の根拠として追跡できる状態を保つ

---

# provenance

Pattern の重要な主張は Markdown から元情報へ追跡できるようにする。

可能な場合は次を記載する。

- Raw の実ファイルパス
- session_id
- 関連する Pattern
- 外部資料を保存している場合はその実ファイルパス

存在しないファイルやパスを provenance に書かない。

根拠関係を DB の中だけに閉じ込めない。

---

# 検索されることを意識して書く

Pattern は `knowledge-base` から検索される。

将来検索に使いそうな正式名称、英語名称、技術用語を本文に自然に含める。

---

# ファイル名

ファイル名だけでも内容と Pattern 種別を推測できる名前を付ける。

推奨:

```text
decision_sqlite_cache.md
incident_wails_linux_ime.md
experiment_strata_parallel.md
experiment_qwen38_vram.md
```

Pattern は `knowledge/wiki/` に保存する。`wiki/` 直下または**領域ディレクトリ**（技術/プロジェクト階層。例: `go/bubbletea/`。小文字英数と `_` `-`、最大3階層）に置く。パターン種別（incident 等）のカテゴリディレクトリは作らない — 種別はファイル名プレフィックスで表現する。領域が不明な Pattern は `wiki/` 直下に置く。

---

# Ingest 手順

1. Raw または現在の作業の本文全体を読み、再利用価値のある知見を判断する（summary で判定しない）
2. `query.md` を使って既存 Pattern を検索する
3. 新規作成か既存 Pattern 更新か判断する
4. `decision-pattern` / `incident-pattern` / `experiment-pattern` から種別を選ぶ
5. 対応するテンプレートを使用する
6. `template/` 配下のテンプレートに従って記述する
7. provenance を記録する
8. `knowledge/wiki/` に保存または既存 Pattern を更新する
9. 意味のある Wiki 変更なら `wiki/log.md` に理由を残す
10. `index.db` に反映する
11. summary を生成・更新する
12. 対象ファイルの Ingest フラグを設定する（下記「Ingest フラグ」）

---

# index.db への反映

Pattern 作成・更新後、索引へ反映する。

```bash
python3 bin/index_markdown.py
```

必要な summary を生成・更新する。

```bash
python3 bin/generate_summary.py
```

コマンドはスキルディレクトリ（`bin/` の親）から実行する。

---

# Ingest フラグ

`index.db` の `documents.ingest_status` に、各 Markdown ファイルの内容確認状態を記録する。

| 値 | 意味 |
| --- | --- |
| `''` | 内容未確認 |
| `patterned` | 内容を確認し、pattern化して wiki に入れた |
| `not_needed` | 内容を確認したが、pattern化不要だった |

設定は `ingested_at`（エポック秒）と `ingested_hash`（Ingest 時点の hash）と同時に行う。
`ingested_hash` は再Ingest 判定（内容が変わったか）に使用する。

手動設定:

```sql
UPDATE documents SET ingest_status = 'patterned', ingested_at = <エポック秒>, ingested_hash = '<Ingest 時点の hash>' WHERE path = '<絶対パス>';
```

Ingest 優先度 `ingest_priority`（0〜3、NULL = 未採点）は generate_summary.py が summary 生成と同一の LLM 呼び出しで採点する。既存 summary だけから採点し直す場合は `generate_summary.py --score-only`。create_pattern.py はこの優先度で候補を並べる。

未確認ファイルの一覧（優先度順）:

```sql
SELECT path, summary, ingest_priority FROM documents WHERE ingest_status = '' ORDER BY COALESCE(ingest_priority, -1) DESC, modified_at ASC;
```

挙動:

- ファイル編集（sync の mtime/hash 更新）ではフラグは保持される
- 同名移動（移動検知で要約再利用）ではフラグ・ingest_priority も引き継がれる
- ファイル消失（DELETE）でフラグも消える。再登録時は `''`
- 設定済みファイルは ingest 後の更新（`modified_at > ingested_at` かつ `hash <> ingested_hash`）で自動的に再Ingest 対象になる。内容が変わらない偽更新（hash 一致）は LLM を呼ばず `ingested_at` のみ更新（hash-skip）
- 内容を変えずに再 Ingest したい場合は手動で `ingest_status` を `''` に戻す

---

# 一括 Ingest（create_pattern.py）

index → summary → pattern の3段パイプラインで一括実行する。

```bash
python3 bin/index_markdown.py
python3 bin/generate_summary.py --limit N
python3 bin/create_pattern.py --limit N
```

- `--limit N` が「見る行数」（処理する新規+再処理対象数。hash-skip 行は制限外）。0 で無制限
- `--path-like PAT` で対象を path LIKE で絞れる（例 `'%bubbletea%'`）
- 内容確認は本文全体を LLM に渡して行う（既定無制限。summary は判定に使わない。`--max-chars` は緊急時の切り詰め用）
- 対象は `ingest_status = ''`（新規）+ `patterned` / `not_needed` で ingest 後に更新された行（`modified_at > ingested_at` かつ `hash <> ingested_hash`。再Ingest。not_needed も再評価）。順序は未確認優先 → `ingest_priority` 高い順（NULL 最後）→ mtime 古い順。ignore_path 該当と `wiki/` 配下自体はスキップ
- LLM が patterned / not_needed を判定し、patterned なら wiki へ書き込む（既存ページへ追記 or 新規作成）。provenance（Raw 実パス）を自動記述し、`wiki/log.md` に追記し、フラグを設定する
- `--dry-run` は判定結果の表示のみで wiki/DB を変更しない。小型モデルの生成品質は限定的なので、まず dry-run でレビューする
- 再Ingest: 成功時に `ingested_hash`（Ingest 時点 hash）を保存し、`wiki/log.md` に再Ingest（ファイル更新）として記録する。クラッシュ復帰は行わない（2026-10-12 決定。再実行で生じた重複セクションは Lint が検出・削除）
- 判定誤りは `ingest_status` を `''` に戻して再実行可能

---

# 矛盾の扱い

既存 Pattern と新しい Raw が矛盾する場合、Ingest の段階で都合よく統合しない。

- 矛盾を記録する
- Lint の対象とする
- 根拠確認後に結論を更新する

---

# 禁止事項

- 分からない事実を補完しない
- 実測していない値を実測値として書かない
- 推測を確定事項として残さない
- 単発事例を根拠なく一般化しない
- 成功した方法だけ残して重要な失敗を消さない
- 環境依存の結果を一般論にしない
- Raw の事実を書き換える目的で Pattern を更新しない
- 同じ知識の Pattern を無意味に増殖させない
- 存在しない Raw、ファイル、パスを provenance に書かない

---

# 完了条件

Ingest は次を満たした時点で完了とする。

- 再利用価値のある知見だけが Pattern 化されている
- 既存 Pattern との重複が確認されている
- 何を判断・理解すべきか分かる
- なぜその結論になったか分かる
- 重要な条件・制約が分かる
- 同じ失敗を避けるための情報がある
- 適用範囲が分かる
- 必要なら再検討条件が分かる
- 根拠となる Raw や資料を追跡できる
- index.db から将来発見できる

最終的な基準:

> **未来の AI がこの Pattern を見つけたとき、今回と同じ調査・失敗・設計判断を最初からやり直さずに済むか。**
