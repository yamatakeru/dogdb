# determinism — 状態を含む決定性への拡張

## MODIFIED Requirements

### Requirement: 決定キーの純粋性
障害の発火判定と内容は、既定では `(policy_version, seed, session_id, template_fingerprint, occurrence, phase)` の純粋関数でなければならない（MUST）。`include_params=True` の場合に限り、HMAC化されたパラメータfingerprintがこの決定入力の末尾に追加される（SHALL）。mood・論理時計・house・stale-read-cacheなどのセッション状態が決定に参加する場合、その状態は `(seed, session_id, セッション開始からの入力列)` のみの純粋関数でなければならない（MUST）。いずれの構成でも、wall-clock時刻、OS乱数、Python組み込み `hash()` を決定に使ってはならない（MUST NOT）。

#### Scenario: 同一入力列は同一イベント列
- **WHEN** 同一seed・同一session_id指定・同一クエリ列で2回実行する
- **THEN** 2つのイベントログは、診断用タイムスタンプを除く全フィールドで一致する

#### Scenario: 状態系を全部有効にしても再現する
- **WHEN** mood・自動返却・OLD_BONEをすべて有効にした同一設定・同一入力列で2回実行する
- **THEN** mood遷移、自動返却のタイミング、stale readの参照先を含むイベント列が完全に一致する

## ADDED Requirements

### Requirement: 乱数導出のdomain separation
決定キーから導出する値（発火判定、行位置、順列、遅延量、保持期間、stale参照先など）は、`SHA-256(decision_key ‖ ":" ‖ 用途タグ)` の形で用途ごとに分離されたハッシュから導出しなければならない（MUST）。用途タグの一覧は契約文書に列挙しなければならない（SHALL）。同一の導出値を複数の用途に流用してはならない（MUST NOT）。例外として、MVP由来のSTASH・SHUFFLE・IGNOREの既存導出は、v1の決定値とイベント列を維持するためv1互換の導出経路を保持しなければならず（SHALL）、この互換経路は当該3障害に閉じて契約文書に明記しなければならない（MUST）。

#### Scenario: 障害同士が不自然に共起しない
- **WHEN** 2つの障害に同じ重みを設定して長いクエリ列を実行する
- **THEN** 各障害の発火判定は独立に導出され、常に同時に発火候補になるような相関は生じない

### Requirement: 保証の単位はセッション先頭からの入力列
決定性の保証は「セッション先頭からの同一の順序付き入力列と同一設定」に対して定義されなければならない（MUST）。途中の操作単体を切り出したreplay（部分replay）の一致は保証の対象外であることを文書化しなければならない（SHALL）。

#### Scenario: 途中から再開しても同じにはならない
- **WHEN** 20操作のセッションの後半10操作だけを新しいセッションとして実行する
- **THEN** 論理時計とmood状態が異なるため、イベント列の一致は保証されない（これは仕様どおりの挙動である）
