# determinism — 決定的障害選択とreplay保証

## ADDED Requirements

### Requirement: 決定キーの純粋性
障害の発火判定と内容は、既定では `(policy_version, seed, session_id, template_fingerprint, occurrence, phase)` の純粋関数でなければならない（MUST）。`include_params=True` の場合に限り、HMAC化されたパラメータfingerprintがこの決定入力の末尾に追加される（SHALL）。いずれの構成でも決定は入力に対する純粋関数であり、wall-clock時刻、OS乱数、Python組み込み `hash()` を決定に使ってはならない（MUST NOT）。

#### Scenario: 同一入力列は同一イベント列
- **WHEN** 同一seed・同一session_id指定・同一クエリ列で2回実行する
- **THEN** 2つのイベントログは、診断用タイムスタンプを除く全フィールドで一致する

### Requirement: パラメータの既定除外とopt-in
既定では、同一SQLテンプレートに異なるバインドパラメータを与えても、同一出現回数における障害決定は同一でなければならない（SHALL）。`include_params=True` を指定した場合に限り、HMAC化されたパラメータfingerprintが決定キーに参加しなければならない（SHALL）。

#### Scenario: 実行ごとに変わるパラメータでも再現する
- **WHEN** 既定設定で、同一テンプレートにUUIDパラメータ（毎回異なる）を与えて2回のrunを実行する
- **THEN** 2つのrunの障害イベント列は一致する

#### Scenario: 忠実モードではパラメータが運命を分ける
- **WHEN** `include_params=True` で、同一テンプレートに異なるパラメータを与える
- **THEN** 両者の `decision_key` は異なる値になる

### Requirement: パラメータfingerprintの入力域
`parameter_fingerprint` の計算は、安定した正規テキスト表現を持つ値のみを受け付けなければならない（MUST）。JSONネイティブ値（null・真偽値・数値・文字列）、および安定した文字列表現を持つ非ネイティブ値（bytes・datetime・Decimal・UUID等）は決定的にエンコードされる（SHALL）。オブジェクト識別子（メモリアドレス等）に依存する表現しか得られない値は、実行前に `TypeError` で拒否されなければならず（MUST）、イベントを記録してはならない（MUST NOT）。この制限は `include_params` の設定に関わらず適用される — `parameter_fingerprint` は全イベントの必須フィールドとして記録されるため、不安定なエンコードは「同一入力列は同一イベント列」の保証を破るからである。

#### Scenario: 不安定な表現しか持たない値は拒否される
- **WHEN** `__repr__` を定義しない任意のオブジェクトをバインドパラメータとして渡す
- **THEN** 実行は `TypeError` で拒否され、イベントは記録されない

#### Scenario: 安定表現を持つ標準型は決定的に処理される
- **WHEN** datetime・Decimal・UUID・bytes を含むパラメータで同一クエリを2回実行する
- **THEN** 両実行のイベントの `parameter_fingerprint` は一致する

### Requirement: 出現回数の管理
同一 `template_fingerprint` の実行はセッション内で出現回数（occurrence）をカウントし、決定キーとイベントに記録しなければならない（MUST）。

#### Scenario: 3回目の実行はoccurrence=3
- **WHEN** 同一クエリをセッション内で3回実行する
- **THEN** イベントの `occurrence` は 1, 2, 3 と記録され、各回の障害決定は独立に行われる

### Requirement: seedの分離
異なるseedを与えた場合、同一操作に対する `decision_key` は異なる値にならなければならない（MUST）。

#### Scenario: seedを変えれば別の犬生
- **WHEN** seed=42 と seed=43 で同一クエリ列を実行する
- **THEN** 対応する操作の `decision_key` は互いに異なる
