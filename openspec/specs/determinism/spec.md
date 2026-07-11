# determinism — 決定的障害選択とreplay保証

## Purpose

同じ入力列から同じ障害決定とイベント列を再現できる決定論的な選択規則を定義し、seed、セッション、SQLテンプレート、出現回数、およびパラメータの扱いを明確にする。

## Requirements

### Requirement: 決定キーの純粋性
障害の発火判定と内容は、既定では `(policy_version, seed, session_id, template_fingerprint, occurrence, phase)` の純粋関数でなければならない（MUST）。`include_params=True` の場合に限り、HMAC化されたパラメータfingerprintがこの決定入力の末尾に追加される（SHALL）。mood・論理時計・house・stale-read-cacheなどのセッション状態が決定に参加する場合、その状態は `(seed, session_id, 正規化済み設定, セッション開始からの入力列)` の純粋関数でなければならない（MUST）。いずれの構成でも、wall-clock時刻、OS乱数、Python組み込み `hash()` を決定に使ってはならない（MUST NOT）。

#### Scenario: 同一入力列は同一イベント列
- **WHEN** 同一seed・同一session_id指定・同一クエリ列で2回実行する
- **THEN** 2つのイベントログは、診断用タイムスタンプを除く全フィールドで一致する

#### Scenario: 状態系を全部有効にしても再現する
- **WHEN** mood・自動返却・OLD_BONEをすべて有効にした同一設定・同一入力列で2回実行する
- **THEN** mood遷移、自動返却のタイミング、stale readの参照先を含むイベント列が完全に一致する

### Requirement: パラメータの既定除外とopt-in
既定では、同一SQLテンプレートに異なるバインドパラメータを与えても、同一出現回数における障害決定は同一でなければならない（SHALL）。`include_params=True` を指定した場合に限り、HMAC化されたパラメータfingerprintが決定キーに参加しなければならない（SHALL）。

#### Scenario: 実行ごとに変わるパラメータでも再現する
- **WHEN** 既定設定で、同一テンプレートにUUIDパラメータ（毎回異なる）を与えて2回のrunを実行する
- **THEN** 2つのrunの障害イベント列は一致する

#### Scenario: 忠実モードではパラメータが運命を分ける
- **WHEN** `include_params=True` で、同一テンプレートに異なるパラメータを与える
- **THEN** 両者の `decision_key` は異なる値になる

### Requirement: パラメータfingerprintの入力域
`parameter_fingerprint` の計算は、次の閉じた許可リストの値のみを受け付けなければならない（MUST）: JSONネイティブ値（null・真偽値・数値・文字列）、および厳密な型一致による `bytes`・`bytearray`・`datetime.date`・`datetime.time`・`datetime.datetime`・`Decimal`・`UUID`。これらは決定的にエンコードされる（SHALL）。サブクラスや独自型を含む上記以外の値は、たとえ安定した表現を持っていても、実行前に `TypeError` で拒否されなければならず（MUST）、イベントを記録してはならない（MUST NOT）。この制限は `include_params` の設定に関わらず適用される — `parameter_fingerprint` は全イベントの必須フィールドとして記録されるため、不安定なエンコードは「同一入力列は同一イベント列」の保証を破るからである。

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

### Requirement: 乱数導出のdomain separation
決定キーから導出する値（発火判定、行位置、順列、遅延量、保持期間、stale参照先など）は、`SHA-256(decision_key ‖ ":" ‖ 用途タグ)` の形で用途ごとに分離されたハッシュから導出しなければならない（MUST）。用途タグの一覧は契約文書に列挙しなければならない（SHALL）。同一の導出値を複数の用途に流用してはならない（MUST NOT）。例外として、MVP由来のSTASH・SHUFFLE・IGNOREの既存導出は、v1の決定値とイベント列を維持するためv1互換の導出経路を保持しなければならず（SHALL）、この互換経路は当該3障害に閉じて契約文書に明記しなければならない（MUST）。

#### Scenario: 障害ごとに別の導出値で判定される
- **WHEN** 2つの障害に同じ重みを設定して同一操作を評価する
- **THEN** 各障害の発火判定は互いに異なる用途タグ（`fire:<FAULT>`）から導出された別の値を使い、同一の導出値が複数の障害の判定に再利用されることはない

### Requirement: 保証の単位はセッション先頭からの入力列
決定性の保証は「セッション先頭からの同一の順序付き入力列と同一設定」に対して定義されなければならない（MUST）。途中の操作単体を切り出したreplay（部分replay）の一致は保証の対象外であることを文書化しなければならない（SHALL）。

#### Scenario: 途中から再開しても同じにはならない
- **WHEN** 20操作のセッションの後半10操作だけを新しいセッションとして実行する
- **THEN** 論理時計とmood状態が異なるため、イベント列の一致は保証されない（これは仕様どおりの挙動である）
