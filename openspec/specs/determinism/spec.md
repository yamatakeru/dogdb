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
`parameter_fingerprint` の計算は、次の閉じた許可リストの値のみを受け付けなければならない（MUST）: JSONネイティブ値（null・真偽値・数値・文字列）、および厳密な型一致による `bytes`・`bytearray`・`datetime.date`・`datetime.time`・`datetime.datetime`・`Decimal`・`UUID`。これらは決定的にエンコードされる（SHALL）。サブクラスや独自型を含む上記以外の値を持つ操作は、fingerprint を計算せず、対応範囲外操作としてバックエンドへ素通ししなければならない（SHALL）。素通しされた操作について decision・イベント・occurrence を生成してはならない（MUST NOT）。入力域外の値を理由に操作を失敗させてはならない（MUST NOT）。不安定な表現から fingerprint を導出してはならず（MUST NOT）、`repr`・pickle・型名によるフォールバック fingerprint を用いてはならない（MUST NOT）。この規則は `include_params` の設定に関わらず適用される — `parameter_fingerprint` は記録される全イベントの必須フィールドであるため、不安定なエンコードを排除する唯一の安全な方法は、当該操作をイベント系列自体に参加させないことである。

#### Scenario: 入力域外の値は素通しされる
- **WHEN** `__conform__` のみを定義した独自型をバインドパラメータとして渡す
- **THEN** 操作はバックエンドへ無介入で委譲され、生接続と同一の結果（または同一のバックエンド例外）が得られ、イベントは記録されない

#### Scenario: 素通しは後続の決定に影響しない
- **WHEN** 同一クエリAを実行し、入力域外パラメータの操作を挟み、再びクエリAを実行する
- **THEN** クエリAの2回の実行の `occurrence` は 1, 2 であり、素通し操作を挟まない場合と同一の `decision_key` になる

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
決定キーから導出する値（発火判定、行位置、順列、遅延量、保持期間、stale参照先など）は、`SHA-256(decision_key ‖ ":" ‖ 用途タグ)` の形で用途ごとに分離されたハッシュから導出しなければならない（MUST）。用途タグの一覧は契約文書に列挙しなければならない（SHALL）。同一の導出値を複数の用途に流用してはならない（MUST NOT）。この規則は全障害に例外なく適用され、特定の障害のための代替導出経路を実装してはならない（MUST NOT）。

#### Scenario: 障害ごとに別の導出値で判定される
- **WHEN** 2つの障害に同じ重みを設定して同一操作を評価する
- **THEN** 各障害の発火判定は互いに異なる用途タグ（`fire:<FAULT>`）から導出された別の値を使い、同一の導出値が複数の障害の判定に再利用されることはない

#### Scenario: MVP由来の3障害も正規形から導出される
- **WHEN** STASH・SHUFFLE・IGNOREのいずれかを評価・適用する
- **THEN** 発火判定は `fire:<FAULT>`、STASHの行位置は `rows:STASH`、SHUFFLEの各交換は `perm:SHUFFLE:<index>` の用途タグから導出され、event ID / treasure IDも他の障害と同一の導出形を使う

### Requirement: 保証の単位はセッション先頭からの入力列
決定性の保証は「セッション先頭からの同一の順序付き入力列と同一設定」に対して定義されなければならない（MUST）。途中の操作単体を切り出したreplay（部分replay）の一致は保証の対象外であることを文書化しなければならない（SHALL）。

#### Scenario: 途中から再開しても同じにはならない
- **WHEN** 20操作のセッションの後半10操作だけを新しいセッションとして実行する
- **THEN** 論理時計とmood状態が異なるため、イベント列の一致は保証されない（これは仕様どおりの挙動である）

### Requirement: セッション状態の不退避
occurrence カウンターおよび fingerprint 単位の統計は、セッション存続中に退避（eviction）や再初期化を行ってはならない（MUST NOT）。これらはセッション内で単調増加であり、退避による occurrence の再利用は同一入力列に対する決定キーを変化させるため禁止される。セッションの想定寿命はテストケースまたは小規模テストスイート単位であり、長時間稼働プロセスへの常設を想定しないことを契約文書に明記しなければならない（SHALL）。

#### Scenario: 大量テンプレートでも退避されない
- **WHEN** セッション内で相異なるSQLテンプレートを大量（例: 10,000種）に実行した後、最初のテンプレートを再実行する
- **THEN** 再実行の `occurrence` は 2 であり、決定キーはテンプレート数の影響を受けない
