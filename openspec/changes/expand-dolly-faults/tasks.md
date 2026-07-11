# Tasks: expand-dolly-faults

段階順は design.md の Migration Plan に従う。各段階の末尾で `uv run pytest` と `openspec validate expand-dolly-faults` を通し、共通適合スイート（DuckDB/SQLite一致）を拡張してから次へ進む。main spec（openspec/specs/）の更新はarchiveフェーズに委ねる。

## 1. 契約とschema v2基盤

- [x] 1.1 `docs/contract-v2.md` を起草する（コアフィールド＋イベント種別別必須フィールド表、fault優先順位の全順序表、domain separation用途タグ一覧、warning outcome語彙）
- [x] 1.2 event writerを `schema_version: 2` へ更新する（`fault_injected` / `treasure_returned` のフィールド集合はv1と同一）
- [x] 1.3 readerのv1/v2混在受理と未知version行の警告スキップを実装する
- [x] 1.4 `limit_exceeded` 警告イベント（行数上限超過で素通しした際の記録）を実装する
- [x] 1.5 検証: v1固定fixtureログとv2追記の混在読み取りテスト、既存全テストの無回帰（`uv run pytest`）

## 2. 合成規則の一般化と設定API

- [x] 2.1 fault優先順位の固定全順序表（phase順→分類順→表順）でDecisionEngineの候補評価を一般化する
- [x] 2.2 乱数導出をdomain separationタグ形式（`SHA-256(decision_key ‖ ":" ‖ tag)`）へ統一する（既存STASH/SHUFFLE/IGNOREの決定値が変わらないことを固定fixtureで担保）
- [x] 2.3 `wrap()` の障害重み辞書の拡張と未知障害名の設定エラーを実装する
- [x] 2.4 スコーピング `only_tables` / `exclude_tables` と分類器のFROMテーブル名抽出（保守的）を実装する
- [x] 2.5 検証: 優先順位競合テスト（ECHO vs CHEW等）、抽出不能文の非対称既定（only指定→対象外 / exclude指定→対象）のテスト

## 3. 形状変異の障害群

- [x] 3.1 ECHO（行複製、`rows_duplicated`）を実装する
- [x] 3.2 TAIL_CHASE（silent切り詰め `rows_truncated` / エラーモード `DollyTailChaseError`・`read_partial`）を実装する
- [x] 3.3 FALSE_EMPTY（列保持の0行、`empty_result`、非粘着）を実装する
- [x] 3.4 分類器にトップレベルLIMIT/OFFSET検出を追加し、PAGE_HOLE（`page_hole`）を実装する
- [x] 3.5 検証: 各障害の決定性テスト（同一seed 2run一致）、houseに宝物が増えないこと、両バックエンドのイベント列一致

## 4. 値変異の障害群

- [x] 4.1 CHEW（プロファイル `utf8_truncate` / `precision_loss` / `nullify`、適合セル選択、details は行番号・列番号・プロファイル名のみ）を実装する
- [x] 4.2 TANGLED_LEASH（隣接列ラベル交換、値は不動）を実装する
- [x] 4.3 WRONG_COUNT（logical rowcountのみ±k改ざん、行データ・backend rowcount不変）を実装する
- [x] 4.4 検証: 適合セルなしで候補外になるテスト、破損前後の値がログに現れないことのgrepテスト、共通適合スイートへtimezone/Decimal/BLOBの値型ケースを追加

## 5. 可用性・時間系の障害群

- [x] 5.1 clock注入（`wrap(..., clock=...)`、既定 `time.sleep`）を実装する
- [x] 5.2 SLOTH（決定的 `delay_ms` 記録、遅延後に実行継続、fault枠消費）を実装する
- [x] 5.3 BARK（`DollyBarkError`）/ GUARD_BOWL（`DollyBusyError`）を実装する（いずれも `not_executed`・retryable=True）
- [x] 5.4 NO_DROP（実行完了後に `DollyNoDropError`・`response_lost`、SELECT限定）を実装する
- [x] 5.5 検証: no-op clockで実時間待ちなしのSLOTHテスト、NO_DROP発火時にバックエンド実行済みであることの検証（副作用のあるSELECTの代替として実行カウンタ付きアダプタスタブを使用）

## 6. mood状態機械

- [x] 6.1 論理時計（全execute/executemanyで加算）とepoch分割を実装する
- [x] 6.2 決定的状態遷移（CALM/SLEEPY/ZOOMY、epoch境界のみ、seed/session/epoch由来）と `mood_changed` イベントを実装する
- [x] 6.3 mood係数表による実効重み変調（既定表＋設定上書き）を実装する
- [x] 6.4 検証: mood無効時のイベント列がmood導入前実装と一致する固定fixtureテスト、mood有効2runの完全一致テスト

## 7. 自動返却とstale-read-cache

- [ ] 7.1 RETURN_TREASURE自動返却（保持期間導出、操作冒頭での返却、`phase="auto_return"`）を実装する
- [ ] 7.2 stale-read-cache（配達済み結果の保持、fingerprintごとリングK＋全体上限、決定的退避、行値のログ非出力）を実装する
- [ ] 7.3 OLD_BONE（過去エントリ必須の候補条件、`stale_read`・`stale_occurrence`）を実装する
- [ ] 7.4 検証: 自動返却タイミングの2run一致、退避の決定性、キャッシュ行値がログファイルに現れないこと、house再建テスト（auto_return含むログ→射影一致）の拡張

## 8. 観測・調査・文書

- [ ] 8.1 `conn.dolly.stats()`（fingerprint単位の分類内訳・介入数、生SQL非含有）を実装する
- [ ] 8.2 `docs/orphan-write-investigation.md` を執筆する（NO_DROPの書き込み拡張の安全条件調査。実装可否の結論を明記し、実装しない結論も可）
- [ ] 8.3 READMEと `examples/` を更新する（新障害の1個ずつ足す導線、mood・auto_return・OLD_BONEのopt-in例、no-op clockのテスト例）
- [ ] 8.4 検証: `openspec validate expand-dolly-faults`、`uv run pytest` 全通過、examplesの実行確認（`uv run python examples/*.py`）
- [ ] 8.5 CodeRabbitレビューを実施し指摘に対応する（AGENTS.md準拠、simplify検討を含む）
