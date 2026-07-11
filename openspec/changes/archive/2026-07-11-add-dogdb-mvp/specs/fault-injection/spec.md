# fault-injection — 障害モデルとエラー型

## ADDED Requirements

### Requirement: STASH（行欠落モード）
STASHが行欠落モードで発火したとき、決定キーから選ばれた行は結果セットから除去されなければならず（SHALL）、除去された行はhouse台帳に宝物として登録され、`fault_injected` イベントが記録されなければならない（SHALL）。対象はSQL分類器がSELECTと分類した文に限る（MUST）。

#### Scenario: 行がハウスへ消える
- **WHEN** 5行を返すSELECTでSTASH（行欠落モード）が行位置2に発火する
- **THEN** 結果は4行になり、位置2の行の値がhouseに保管され、イベントログに `fault: "STASH"` が記録される

### Requirement: STASH（エラーモード）
STASHがエラーモードに設定されて発火したとき、結果を返す代わりに `DollyStashedError` を送出しなければならない（SHALL）。エラーは機械可読属性（event_id, fault, phase, retryable, outcome）を持たなければならない（MUST）。

#### Scenario: 取得がドリーに阻まれる
- **WHEN** エラーモードのSTASHがSELECTに発火する
- **THEN** `DollyStashedError` が送出され、`str(error)` に犬の物語（例: "Dolly took row #7 to her house."）が含まれ、属性で fault と event_id が参照できる

### Requirement: SHUFFLE（順序攪乱）
SHUFFLEは、トップレベルに `ORDER BY` を持たないと分類されたSELECTの結果行順を、決定キー由来の順列で並べ替えなければならない（SHALL）。`ORDER BY` 付きと分類された文には適用してはならない（MUST NOT）。

#### Scenario: 暗黙順序依存を炙り出す
- **WHEN** `ORDER BY` なしのSELECTにSHUFFLEが発火する
- **THEN** 行の集合は不変のまま、順序が決定キーから導出された順列に置き換わる

#### Scenario: ORDER BYは尊重される
- **WHEN** `SELECT ... ORDER BY id` を実行する
- **THEN** SHUFFLEは適用されず、順序はバックエンドの返却どおりになる

### Requirement: IGNORE（lost request）
IGNOREは文の実行**前**に発火し、バックエンドへ文を送らずに `DollyIgnoredError`（outcome="not_executed", retryable=True）を送出しなければならない（SHALL）。バックエンド側の状態は一切変化してはならない（MUST NOT）。

#### Scenario: 眠いドリーはINSERTを無視する
- **WHEN** INSERTにIGNOREが発火する
- **THEN** `DollyIgnoredError` が送出され、テーブルの行数は変化せず、リトライ（出現回数が進み決定キーが変わる）で成功し得る

### Requirement: 1操作1 fault と優先順位
1回の操作で適用される障害は最大1つでなければならない（MUST）。複数の障害が発火候補となった場合、failure injection（STASHエラーモード、IGNORE）が silent mutation（STASH行欠落、SHUFFLE）に優先しなければならない（SHALL）。

#### Scenario: 候補が競合しても1つだけ
- **WHEN** 同一操作でIGNOREとSHUFFLEの両方が発火候補になる
- **THEN** IGNOREのみが適用され、イベントログに記録される fault は1件である

### Requirement: 障害確率の設定
`wrap()` は障害ごとの発火確率設定を受け付けなければならない（SHALL）。確率0はその障害を無効化しなければならない（MUST）。

#### Scenario: 全確率0で無風
- **WHEN** 全障害の確率を0にして任意のクエリ列を実行する
- **THEN** fault イベントは一件も記録されず、結果は素の接続と完全に一致する

### Requirement: エラー型階層と実DBエラーの透過
注入エラーはすべて `DogDBError` 基底のサブクラスでなければならない（MUST）。バックエンド由来の実エラーはラップせず素通ししなければならず（SHALL）、`isinstance(e, DogDBError)` で注入と実障害を判別できなければならない（MUST）。楽しい文言は `str(error)` のみに置き、テストの制御は属性で行えなければならない（SHALL）。

#### Scenario: 本物のSQLエラーは素通し
- **WHEN** 構文エラーのあるSQLを実行する
- **THEN** バックエンド固有の例外が送出され、それは `DogDBError` のインスタンスではない
