# move-detection.md

## 目的

ファイルを移動（同じ名前のまま場所変更）したとき、summary と ingest_status を失わない。

## 仕組み

1. sync 時に全ファイルの hash（xxh64）を `xxhsum --filelist` で一括計算し documents.hash に保存
2. 新規 path の INSERT 前に `find_reusable()` を実行:
    - 条件: hash 一致 + 同じ basename（`path LIKE '%/'+basename`）+ `summary <> ''` + 自分以外の path
    - 複数候補（同名同一hash）は summary_at 最新を1件採用
3. 一致があれば summary / summary_at / ingest_status をコピーして INSERT。旧 path の行は DELETE

## 引き継がれるもの

- summary / summary_at
- ingest_status / ingested_at（Ingest 済みなら再 pattern 化されない）

## 限界

- **改名（basename 変更）は検知しない**。新行は summary='' / ingest_status='' で増えるだけ。旧行は DELETE される（2026-10-12 の D10 命名則移行で実証: 本文無変更の mv 16件で reused: 0。`generate_summary.py` で再生成した）
- 引き継ぎには旧行の `summary <> ''` が必要。パイプライン上 summary 生成後なので実運用では成立する
- 同名同一hash が複数ある場合は summary_at 最新1件のみ採用（他は残存。lint の対象）
- **移動と同時に本文を編集すると hash が変わり reuse 不発**（2026-10-12 の D9 移行で実証: provenance 書き換えを mv と同時に行ったため reused:1、要約喪失）。回避策: ① mv → sync → 本文編集 → sync（2回目の sync は UPDATE のみで flags 保持）の順で行う。② 失われた場合は `generate_summary.py` で再生成可能（ingest_status は Raw 側の行に残るので pattern 化はやり直しにならない）

## 関連

- 設計調査の記録: task_archive.md（ファイル移動検知セクション）
- hash 計算・find_reusable 実装: bin/index_markdown.py
