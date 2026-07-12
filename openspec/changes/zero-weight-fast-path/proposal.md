## Why

全障害の確率が0でも、全executeでSQL分類・SHA-256複数回・HMACが走る。`_fires` は確率チェックの**前**に無条件で発火判定ハッシュを導出し、`template_fingerprint` は統計記録用（proxy）と決定用（`DecisionEngine.begin`）で二重計算され、`parameter_fingerprint`（HMAC）は使われない場合も毎操作計算される。実測ではゼロ確率の小SELECT 2000回で素15ms→ラップ455ms（約30倍）。「まず全確率0で導入し、テストを変えずに障害を有効化する」という推奨導線において、この無条件オーバーヘッドが採用障壁になる。

## What Changes

- 実効重み（base重み × mood係数）が0の障害は、発火判定の導出ハッシュを計算する前に即除外する。
- 操作のどの観測可能な出力にも寄与しない場合、decision key の導出自体をスキップする（`decide()` は副作用のない純関数のため観測不能）。occurrence カウント・SQL分類・統計記録・論理時計の前進は**fast pathでも維持する**。
- `template_fingerprint` の二重計算を解消し、1操作1回にする。
- `parameter_fingerprint` を遅延評価にする（include_params=True の決定入力、イベント・宝物・staleエントリ・デバッグイベントの生成時に初回解決、1操作最大1回）。
- ゼロ実効重み時のオーバーヘッド上限（素の5倍以内）と計算回避を要件化し、再現可能なベンチマークスクリプトを追加する。

### Non-goals

- 決定値・イベント列・統計の一切の変更（**非破壊**。W3-a確定のv3基準線に対しdecision key / fault / occurrence / イベント / 論理結果 / statsのbyte-for-byte一致が合格ゲート）。
- `classify_sql` と統計記録の省略（切るとUNKNOWN率・corpus計測が失われるため維持する——統括issueのパネル審議で決定済み）。
- mood導出・エポック遷移コストの最適化（mood有効時はゼロ確率導線の外）。
- 素通し判定（`params_in_fingerprint_domain` 等）の変更（W1-bで確定済みの挙動を保つ）。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `dbapi-proxy`: ゼロ実効重み時の計算回避とオーバーヘッド上限をADDED要件として追加する（既存要件の変更はなし。分類・統計・occurrence・論理時計の維持は既存要件を参照し、性能上限と導出計算の禁止を新設する）。

## Impact

- **コード**: `src/dogdb/core/faults.py`（`_fires` の評価順）、`src/dogdb/core/decision.py`（`begin` のfingerprint受け渡し・遅延化）、`src/dogdb/proxy/connection.py`（`execute` のphaseスキップ述語・fingerprint一回計算）。
- **テスト**: 既存全テストは無変更で通ること自体が合格ゲート（byte-for-byte一致）。追加はfast path固有の性質テスト（重み0→非0の実行時変更後もdecision keyが純関数として不変、include_params=True・debug=True・stale cache有効時の各経路でイベントが従来どおり出る）。
- **ベンチマーク**: `benchmarks/zero_weight_overhead.py` を新設（CI断言にはしない。測定条件を固定し、PRに実測値を記録する）。
- **制約**: `FaultPolicy` は実行時可変（プロパティsetterが公開されテストで実使用）のため、実効重みの判定は操作ごと・phaseごとに評価し、wrap時にキャッシュしてはならない。
- **依存関係**: W3-a（policy-v3-derivation-cleanup）の完了が前提（ゴールデン基準線の確定後に着手。先にやるとゴールデンを二度作り直す）。W1-bの素通し確定にも依存（済み）。
