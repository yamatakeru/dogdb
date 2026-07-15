# dbapi-proxy — delta: max-result-rows-safeguard

## ADDED Requirements

### Requirement: max_result_rowsによる中断的読み取り
`wrap()` は省略可能な引数 `max_result_rows`（既定 `None`）を受け付けなければならない（SHALL）。`None`（既定）の場合、挙動は本Requirement導入前と完全に同一でなければならない（MUST）。値を指定した場合、対象は `max_intervention_rows` 検査と同一のスコープ（分類器がSELECTと判定し、`only_tables` / `exclude_tables` スコープに含まれる操作）に限る（SHALL）。バックエンドから結果を読み取る過程で `max_result_rows + 1` 行目を観測した時点で読み取りを中断しなければならず（MUST）、それ以降の行を取得してはならない（MUST NOT）。中断時、呼び出し側へ部分的な結果を返してはならない（MUST NOT）。中断が発生した場合、`limit_exceeded` イベント（`details.limit = "max_result_rows"`、`details.configured` に設定値、`details.observed = "exceeded"`）を記録した上で（SHALL）、非retryableな `DollyLimitError` を送出しなければならない（SHALL）。この判定はバックエンド上でクエリの実行が開始済みである状態で発生する点を契約文書とREADMEに明記しなければならない（SHALL）。

#### Scenario: 上限未満は中断しない
- **WHEN** `max_result_rows=5` の設定で3行を返すSELECTを実行する
- **THEN** 中断は発生せず、3行が通常どおり返る

#### Scenario: 上限ちょうどは中断しない
- **WHEN** `max_result_rows=3` の設定で3行を返すSELECTを実行する
- **THEN** 中断は発生せず、3行が通常どおり返る

#### Scenario: 上限超過は部分結果なしで中断する
- **WHEN** `max_result_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** 3行目の観測時点で読み取りが中断し、呼び出し側は行を1件も受け取らず、`details` に `limit="max_result_rows"`・`configured=2`・`observed="exceeded"` を含む `limit_exceeded` イベントが記録された上で、非retryableな `DollyLimitError` が送出される

### Requirement: max_result_rowsとmax_intervention_rowsの直交性
`max_result_rows` と `max_intervention_rows` は独立したノブでなければならず（MUST）、両者の間に結合バリデーションを設けてはならない（MUST NOT）。一方の設定値が他方の挙動を変えてはならない（MUST NOT）。両方を同時に設定できなければならない（SHALL）。

#### Scenario: 両方設定時も独立に評価される
- **WHEN** `max_intervention_rows=2` かつ `max_result_rows=10` の設定で5行を返すSELECTを実行する
- **THEN** `max_result_rows` は超過しないため読み取りは中断されず、`max_intervention_rows` 超過による通常の `limit_exceeded`（`details.limit="max_intervention_rows"`）経路のみが独立に評価される

#### Scenario: 設定値の組み合わせを拒否しない
- **WHEN** `max_result_rows=100` かつ `max_intervention_rows=100000`（大小関係が逆転する設定）で `wrap()` を呼ぶ
- **THEN** 設定エラーは発生せず、接続は正常にラップされる

### Requirement: max_result_rows中断時の決定性とfault評価順序
`max_result_rows` による中断は、同一DB状態・同一seed・同一session_id・同一入力列であれば決定的に再現しなければならない（MUST）。中断が発生した操作でも、occurrenceカウンタと論理時計（mood・自動返却）は他の操作と同様に前進しなければならない（MUST）。中断時は `on_result` phaseの障害候補選択（`FaultEngine.on_result` によるfault適用の評価）を行ってはならず（MUST NOT）、当該操作について `decision_evaluated` イベントを記録してはならない（MUST NOT）。`before_execute` phaseの障害（BARK・GUARD_BOWL・IGNORE・SLOTH）は、`max_result_rows` による中断より先に評価され得る（SHALL）。

#### Scenario: 中断も決定的に再現する
- **WHEN** 同一seed・同一DB状態・同一SQL列で `max_result_rows` 超過を2回再現する
- **THEN** 両回とも同一occurrenceで中断し、記録される `limit_exceeded` イベントは診断用タイムスタンプを除く全フィールドで一致する

#### Scenario: occurrenceと論理時計は中断時も進む
- **WHEN** mood有効時のセッションで、同一テンプレートを2回実行し、2回目で `max_result_rows` 超過による中断が発生する
- **THEN** 2回目の操作の `occurrence` は2であり、mood遷移の論理時計は中断した操作も1操作として数える

#### Scenario: BARKは中断より先に発火し得る
- **WHEN** `before_execute` phaseでBARKが発火する設定かつ `max_result_rows` 超過が見込まれるSELECTを実行する
- **THEN** `DollyBarkError` が送出され、バックエンドへ文は送られず、`max_result_rows` による中断（`limit_exceeded` イベント・`DollyLimitError`）は発生しない

#### Scenario: 中断時はdecision_evaluatedが記録されない
- **WHEN** `debug=True` かつ `max_result_rows` 超過による中断が発生する
- **THEN** `limit_exceeded` イベントは記録されるが、当該操作について `decision_evaluated` イベントは記録されない
