# fault-injection — delta for fault-taxonomy

## ADDED Requirements

### Requirement: 機械可読taxonomy（category / severity）
全障害は、閉じた語彙による機械可読の分類を持たなければならない（SHALL）: `category` は `failure_injection`（呼び出しそのものの失敗）・`temporal`（応答時間）・`shape`（結果の行集合・順序）・`value`（結果の値・ラベル・件数報告）・`state`（時間的一貫性）のいずれか、`severity` は `error`（例外として可視）・`silent_corruption`（例外なしに結果が破損）・`delay`（結果は無傷で遅延のみ）のいずれかである（SHALL）。モードを持つ障害（STASH・TAIL_CHASE）は発火モードごとに値を定め、全障害（モード分岐含む）と（category, severity）の対応表を契約文書に列挙しなければならない（SHALL）。対応表は障害語彙（KNOWN_FAULTS）と一対一であることが機械検証されなければならない（MUST）。語彙・対応表の拡張は仕様変更を要する（SHALL）。category / severity は decision key の導出入力に参加してはならない（MUST NOT）。注入例外は読み取り専用属性 `category` / `severity` を持たなければならず（SHALL）、fault 由来でない例外（介入上限超過）では両属性は None でなければならない（SHALL）。新障害の追加時は「犬の行動 × 1語で結果形状が想像できる」命名基準を満たし、対応表への同時登録を行わなければならない（MUST）。

#### Scenario: サイレント破損系を1属性で拾える
- **WHEN** CHEW が発火し `fault_injected` イベントが記録される
- **THEN** イベントの `severity` は `silent_corruption`、`category` は `value` である

#### Scenario: 例外の分類属性は読み取り専用
- **WHEN** BARK が発火して送出された例外の `category` を参照し、次に代入を試みる
- **THEN** `category == "failure_injection"` かつ `severity == "error"` であり、代入は `AttributeError` で拒否される

#### Scenario: モード分岐は発火モードで分類される
- **WHEN** `stash_mode="missing"` で STASH が発火した場合と、`stash_mode="error"` で発火した場合を比較する
- **THEN** 前者のイベントは `category == "shape"` / `severity == "silent_corruption"`、後者の例外とイベントは `category == "shape"` / `severity == "error"` である

#### Scenario: decision keyは不変
- **WHEN** taxonomy 導入済みの実装で policy v3 golden 回帰テストを実行する
- **THEN** 全 decision key・イベントの既存フィールドは golden と一致する

#### Scenario: 介入上限超過はfault分類を持たない
- **WHEN** `on_max_rows="error"` で上限超過により `DogDBError` 派生例外が送出される
- **THEN** 例外の `category` と `severity` はいずれも None である

## MODIFIED Requirements

### Requirement: エラー型階層と実DBエラーの透過
注入エラーはすべて `DogDBError` 基底のサブクラスでなければならない（MUST）。バックエンド由来の実エラーはラップせず素通ししなければならず（SHALL）、`isinstance(e, DogDBError)` で注入と実障害を判別できなければならない（MUST）。楽しい文言は `str(error)` のみに置き、テストの制御は属性で行えなければならない（SHALL）。機械可読属性には `event_id`・`fault`・`phase`・`retryable`・`outcome` に加えて `category`・`severity` を含めなければならない（SHALL）。

#### Scenario: 本物のSQLエラーは素通し
- **WHEN** 構文エラーのあるSQLを実行する
- **THEN** バックエンド固有の例外が送出され、それは `DogDBError` のインスタンスではない

#### Scenario: 注入エラーは属性で制御できる
- **WHEN** GUARD_BOWL が発火して例外が送出される
- **THEN** 例外は `event_id`・`fault`・`phase`・`retryable`・`outcome`・`category`・`severity` を属性として持ち、テストは文言に依存せず分岐できる
