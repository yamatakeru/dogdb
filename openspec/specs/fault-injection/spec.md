# fault-injection — 障害モデルとエラー型

## Purpose

DogDBが注入するSTASH、SHUFFLE、IGNORE各障害の適用条件、優先順位、結果、および実データベースエラーとの機械的な区別を定義する。

## Requirements

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
1回の操作で適用される障害は最大1つでなければならない（MUST）。評価はphase順に行い、`before_execute` で failure injection（BARK、GUARD_BOWL、IGNORE）が発火した場合、文を実行してはならない（MUST NOT）。SLOTHは `before_execute` で発火しても遅延後に実行を継続し、その操作のfault枠を消費する（SHALL）。`on_result` の候補は、契約文書に記載された固定の全順序 — failure injection（NO_DROP、STASHエラーモード）、形状変異（STASH行欠落、FALSE_EMPTY、TAIL_CHASE、PAGE_HOLE、ECHO、SHUFFLE）、値変異（TANGLED_LEASH、CHEW、WRONG_COUNT）、状態系（OLD_BONE）の順 — で評価し、最初に発火した1つだけを適用しなければならない（SHALL）。前提条件を満たさない障害は発火候補になってはならない（MUST NOT）。

#### Scenario: 候補が競合しても1つだけ
- **WHEN** 同一操作でIGNOREとSHUFFLEの両方が発火候補になる
- **THEN** IGNOREのみが適用され、イベントログに記録される fault は1件である

#### Scenario: 優先順位は固定表に従う
- **WHEN** 同一操作でECHOとCHEWの両方が発火候補になる
- **THEN** 形状変異であるECHOだけが適用され、同一入力列の再実行でも常に同じ選択になる

### Requirement: 障害確率の設定
`wrap()` は障害ごとの発火重み（base重み）設定を受け付けなければならない（SHALL）。設定されない障害の重みは0でなければならず（MUST）、重み0はその障害を無効化しなければならない（MUST）。mood有効時の実効重みは base重み × mood係数 で計算される（SHALL）。スコーピング設定 `only_tables` / `exclude_tables` が与えられた場合、分類器が抽出したテーブル名に基づいて障害適用の対象を制限しなければならない（SHALL）。テーブル名を抽出できない文は、`only_tables` 指定時は対象外、`exclude_tables` 指定時は対象としなければならない（MUST）。`only_tables` と `exclude_tables` の同時指定は意味が曖昧なため、設定エラーとして拒否しなければならない（MUST）。

#### Scenario: 全確率0で無風
- **WHEN** 全障害の確率を0にして任意のクエリ列を実行する
- **THEN** fault イベントは一件も記録されず、結果は素の接続と完全に一致する

#### Scenario: 対象テーブルを絞る
- **WHEN** `only_tables=["orders"]` を指定し、`orders` と `users` へのSELECTを実行する
- **THEN** 障害は `orders` への文にのみ発火し得て、テーブル名を抽出できない複文には発火しない

### Requirement: エラー型階層と実DBエラーの透過
注入エラーはすべて `DogDBError` 基底のサブクラスでなければならない（MUST）。バックエンド由来の実エラーはラップせず素通ししなければならず（SHALL）、`isinstance(e, DogDBError)` で注入と実障害を判別できなければならない（MUST）。楽しい文言は `str(error)` のみに置き、テストの制御は属性で行えなければならない（SHALL）。機械可読属性には `event_id`・`fault`・`phase`・`retryable`・`outcome` に加えて `category`・`severity` を含めなければならない（SHALL）。

#### Scenario: 本物のSQLエラーは素通し
- **WHEN** 構文エラーのあるSQLを実行する
- **THEN** バックエンド固有の例外が送出され、それは `DogDBError` のインスタンスではない

#### Scenario: 注入エラーは属性で制御できる
- **WHEN** GUARD_BOWL が発火して例外が送出される
- **THEN** 例外は `event_id`・`fault`・`phase`・`retryable`・`outcome`・`category`・`severity` を属性として持ち、テストは文言に依存せず分岐できる

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

### Requirement: ECHO（重複配達）
ECHOが発火したとき、決定キーから選ばれた1行を結果セット内の直後の位置に複製しなければならない（SHALL）。元の行集合から行を失わせてはならない（MUST NOT）。対象はSQL分類器がSELECTと分類した文に限る（MUST）。

#### Scenario: 同じおもちゃを2回見せる
- **WHEN** 5行を返すSELECTでECHOが行位置1に発火する
- **THEN** 結果は6行になり、位置1と位置2が同一の行値を持ち、イベントに `outcome: "rows_duplicated"` が記録される

### Requirement: TAIL_CHASE（途中で帰る）
TAIL_CHASEはsilentモードとエラーモードを持たなければならない（MUST）。silentモードでは決定キーから導出したk行（k≥1）を結果末尾から切り詰め、`outcome: "rows_truncated"` を記録しなければならない（SHALL）。エラーモードでは `DollyTailChaseError`（outcome="read_partial"）を送出し、届いた行数を `details` に記録しなければならない（SHALL）。いずれのモードでも切り詰めは粘着せず、house台帳に宝物を登録してはならない（MUST NOT）。

#### Scenario: 遊びの途中で帰る（silent）
- **WHEN** 5行を返すSELECTでsilentモードのTAIL_CHASEが発火する
- **THEN** 結果は先頭から連続する5未満の行数になり、同一クエリの再実行（次のoccurrence）では独立に決定される

#### Scenario: 途中でリードが切れる（エラー）
- **WHEN** エラーモードのTAIL_CHASEが発火する
- **THEN** `DollyTailChaseError` が送出され、属性から outcome="read_partial" と届いた行数が参照できる

### Requirement: FALSE_EMPTY（ないよと嘘をつく）
FALSE_EMPTYが発火したとき、列名を保ったまま0行の結果を返さなければならない（SHALL）。隠した行をhouse台帳へ登録してはならず（MUST NOT）、同一クエリの次のoccurrenceの決定は独立でなければならない（MUST）。

#### Scenario: 再試行で見つかる嘘
- **WHEN** 3行を返すSELECTでFALSE_EMPTYが発火し、同一クエリを再実行して発火しない
- **THEN** 1回目は列名付きの0行、2回目は3行が返り、イベントには `outcome: "empty_result"` が1件だけ記録される

### Requirement: PAGE_HOLE（ページを1枚食べた）
PAGE_HOLEは、SQL分類器がトップレベルのリテラル `LIMIT` / `OFFSET`（OFFSET>0）を検出できたSELECTのみを対象としなければならない（MUST）。発火時はページ先頭側の行を決定キー由来で1行以上除去しなければならない（SHALL）。検出できない文に適用してはならない（MUST NOT）。

#### Scenario: 2ページ目の先頭が消える
- **WHEN** `SELECT ... LIMIT 10 OFFSET 10` にPAGE_HOLEが発火する
- **THEN** 返る行数は10未満になり、イベントに `outcome: "page_hole"` が記録される

#### Scenario: OFFSETがなければ対象外
- **WHEN** OFFSET句のないSELECTを実行する
- **THEN** PAGE_HOLEは発火候補にならない

### Requirement: CHEW（値破損の閉じたプロファイル）
CHEWの変異は閉じたプロファイル集合 `utf8_truncate`（文字列の切り詰め）、`precision_loss`（数値の精度損失）、`nullify`（NULL化）のみでなければならない（MUST）。対象セルはプロファイルに適合する型のセルから決定キーで選び、適合セルが存在しない結果では発火候補になってはならない（MUST NOT）。`details` には行番号・列番号・プロファイル名のみを記録し、破損前後の値を記録してはならない（MUST NOT）。

#### Scenario: 文字列を噛む
- **WHEN** 文字列列を含む結果に `utf8_truncate` プロファイルのCHEWが発火する
- **THEN** 選ばれたセルの文字列が短くなり、イベントの `details` に行番号・列番号・プロファイル名だけが記録される

#### Scenario: 噛める型がなければ発火しない
- **WHEN** 整数列のみの結果に対して `utf8_truncate` プロファイルだけが設定されている
- **THEN** CHEWは発火候補にならず、他の障害決定に影響しない

### Requirement: TANGLED_LEASH（列ラベルの取り違え）
TANGLED_LEASHが発火したとき、`LogicalResult` の隣接する2つの列**名**を入れ替えなければならない（SHALL）。行の値を移動してはならない（MUST NOT）。列が1つ以下の結果では発火候補になってはならない（MUST NOT）。

#### Scenario: リードが絡まって名札が入れ替わる
- **WHEN** `SELECT 1 AS a, 2 AS b` にTANGLED_LEASHが発火する
- **THEN** 列名は `["b", "a"]` になり、行値は `(1, 2)` のままである

### Requirement: WRONG_COUNT（数え間違い）
WRONG_COUNTが発火したとき、分類済みSELECTのlogical rowcountのみを決定キー由来の差分（下限0）で改ざんしなければならない（SHALL）。行データおよびバックエンドのrowcountを変更してはならない（MUST NOT）。`details` には報告値と実際の行数を記録しなければならない（MUST）。

#### Scenario: 3個を4個と数える
- **WHEN** 3行を返すSELECTにWRONG_COUNTが発火する
- **THEN** 取得できる行は3行のまま、プロキシのrowcountは3以外の値を報告し、イベントに両方の値が記録される

### Requirement: BARK（一時エラー）
BARKは文の実行前に発火し、バックエンドへ文を送らずに `DollyBarkError`（outcome="not_executed", retryable=True）を送出しなければならない（SHALL）。バックエンド側の状態は一切変化してはならない（MUST NOT）。

#### Scenario: 吠えられて近づけない
- **WHEN** SELECTにBARKが発火する
- **THEN** `DollyBarkError` が送出され、リトライ（次のoccurrence）は独立に決定される

### Requirement: GUARD_BOWL（busy / lock timeout）
GUARD_BOWLは文の実行前に発火し、`DollyBusyError`（outcome="not_executed", retryable=True）を送出しなければならない（SHALL）。BARKとはエラー型で機械的に区別できなければならない（MUST）。

#### Scenario: 餌皿は渡さない
- **WHEN** GUARD_BOWLが発火する
- **THEN** `DollyBusyError` が送出され、`isinstance` でBARK由来の `DollyBarkError` と区別できる

### Requirement: NO_DROP（lost response）
NO_DROPは分類済みSELECTをバックエンドで実行**完了させた後**、結果を渡さずに `DollyNoDropError`（outcome="response_lost", retryable=True）を送出しなければならない（SHALL）。本changeでは書き込み文に適用してはならない（MUST NOT）。イベントの `phase` は `on_result` でなければならない（MUST）。

#### Scenario: 取ってきたのに渡さない
- **WHEN** SELECTにNO_DROPが発火する
- **THEN** バックエンドでは実行済みだが `DollyNoDropError` が送出され、イベントには実行済みであることを示す `outcome: "response_lost"` が残る

### Requirement: SLOTH（寝たふり）
SLOTHが発火したとき、決定キーから導出した遅延量を `details` の `delay_ms` に記録し、注入されたclockを通じてのみ実時間の遅延を発生させなければならない（SHALL）。遅延後、操作は通常どおり実行され、SLOTHがその操作のfault枠を消費しなければならない（MUST）。遅延量の決定にwall-clockを使ってはならない（MUST NOT）。

#### Scenario: no-op clockなら待たずに検証できる
- **WHEN** no-op clockを注入したセッションでSLOTHが発火する
- **THEN** テストは実時間を待たずに完了し、イベントの `delay_ms` に決定的な遅延量が記録され、結果は無遅延実行と同一である

### Requirement: OLD_BONE（stale read）
OLD_BONEが発火したとき、stale-read-cacheに保持された同一鍵の過去occurrenceの配達済み結果を返さなければならない（SHALL）。当該操作のバックエンド実行結果は破棄し、イベントには `outcome: "stale_read"` と参照した `stale_occurrence` を記録しなければならない（MUST）。

#### Scenario: 埋めた骨の味がする
- **WHEN** データを更新した後、同一SELECTの再実行でOLD_BONEが発火する
- **THEN** 更新前に配達された結果と同一の行が返り、イベントから何回目の結果を再演したかが追跡できる
