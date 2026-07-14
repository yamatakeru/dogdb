# DogDB contract v2

この文書は DogDB v2 の相互運用契約である。キーワード MUST / MUST NOT / SHALL は拘束要件を表す。v1 の履歴契約は `docs/contract-v1.md` に残す。

## 決定関数と fingerprint

`decision_key`、SQL template fingerprint、parameter fingerprint の定義は contract v1 を継承する。`POLICY_VERSION` は `dogdb-v4:normalize=trim+collapse-whitespace+lowercase-preserve-literals` である。決定性の保証単位は、同一 seed、明示した同一 session ID、同一設定、およびセッション先頭からの同一の順序付き入力列である。部分 replay の一致は保証しない。

parameter fingerprint の入力域は、JSONネイティブのscalar値と、厳密な型一致による `bytes`、`bytearray`、`datetime.date`、`datetime.time`、`datetime.datetime`、`Decimal`、`UUID` に閉じる。サブクラスや独自型を含む入力域外の位置パラメータ操作は、fingerprint、decision、event、occurrenceを生成せずバックエンドへ素通しする。素通し操作でもmood／自動返却の論理時計は1操作として進める。発生数は `dolly.stats()["passthrough"]["unsupported_parameter_type"]` に記録し、生パラメータ、型名、reprを統計へ含めてはならない。将来この操作を障害注入対象にする場合は、occurrenceとreplay系列が変わるため、`POLICY_VERSION` 更新の要否を判断しなければならない。

occurrence カウンタおよび fingerprint 単位の統計はセッション中に退避または再初期化してはならず、単調増加する。occurrence の再利用は決定キーを変えるためである。DuckDB のセッションは親接続と全 `cursor()` クローンを横断する `execute()` 呼び出しの全順序であり、stats・house・イベントログ・論理時計は意図して合算する。セッションはテストケースまたは小規模テストスイート単位で作り直し、長時間稼働プロセスへ常設しない。

決定キーから用途別の値を得る標準導出は次式とする。

```text
derived(tag) = SHA-256(UTF-8(decision_key + ":" + tag))
```

wall-clock、OS 乱数、Python の組み込み `hash()` を決定へ使ってはならない。各用途は次の閉じたタグまたはタグ形式を使い、異なる用途間で導出値を流用してはならない。

| tag / pattern | purpose |
|---|---|
| `fire:<FAULT>` | 障害ごとの発火判定 |
| `rows:STASH` | STASH の行位置 |
| `rows:ECHO` | ECHO の複製行位置 |
| `rows:TAIL_CHASE` | TAIL_CHASE の切り詰め行数 |
| `rows:PAGE_HOLE` | PAGE_HOLE の除去行数 |
| `perm:SHUFFLE:<index>` | Fisher–Yates の各交換位置 |
| `cell:CHEW` | CHEW の対象セル |
| `profile:CHEW` | CHEW のプロファイル選択 |
| `columns:TANGLED_LEASH` | 交換する隣接列 |
| `count:WRONG_COUNT` | logical rowcount の差分 |
| `delay:SLOTH` | SLOTH の遅延量 |
| `hold:RETURN` | RETURN_TREASURE の保持期間 |
| `stale:OLD_BONE` | OLD_BONE の参照 occurrence |
| `mood:<epoch>` | epoch ごとの mood 遷移 |
| `event:<seq>:<event-name>` | event ID |
| `treasure:<row-index>` | treasure ID |

`category` と `severity` は障害の説明属性であり、上の決定タグ表および
decision key の導出入力には加えない。taxonomy の追加によって
`POLICY_VERSION` や既存の決定キーを変更してはならない。

## fault 合成規則

1操作へ適用する fault は最大1つとする。候補は次の固定全順序で評価し、前提条件を満たし、かつ発火した最初の1件だけを適用する。未指定の障害の base weight は0である。

| order | phase | category | severity | fault |
|---:|---|---|---|---|
| 1 | `before_execute` | `failure_injection` | `error` | BARK |
| 2 | `before_execute` | `failure_injection` | `error` | GUARD_BOWL |
| 3 | `before_execute` | `failure_injection` | `error` | IGNORE |
| 4 | `before_execute` | `temporal` | `delay` | SLOTH |
| 5 | `on_result` | `failure_injection` | `error` | NO_DROP |
| 6 | `on_result` | `shape` | `error` | STASH（error mode） |
| 7 | `on_result` | `shape` | `silent_corruption` | STASH（missing mode） |
| 8 | `on_result` | `shape` | `silent_corruption` | FALSE_EMPTY |
| 9 | `on_result` | `shape` | `error`（error mode）／`silent_corruption`（silent mode） | TAIL_CHASE |
| 10 | `on_result` | `shape` | `silent_corruption` | PAGE_HOLE |
| 11 | `on_result` | `shape` | `silent_corruption` | ECHO |
| 12 | `on_result` | `shape` | `silent_corruption` | SHUFFLE |
| 13 | `on_result` | `value` | `silent_corruption` | TANGLED_LEASH |
| 14 | `on_result` | `value` | `silent_corruption` | CHEW |
| 15 | `on_result` | `value` | `silent_corruption` | WRONG_COUNT |
| 16 | `on_result` | `state` | `silent_corruption` | OLD_BONE |

`before_execute` の failure injection が発火した場合は backend を実行しない。SLOTH は遅延後に backend 実行を続けるが、その操作の fault 枠を消費する。`on_result` は backend 実行後に評価する。STASH はエラーモードと行欠落モードが別個の評価候補（order 6・7）だが、TAIL_CHASE は単一の評価候補（order 9）であり、モードは適用時の効果と分類のみを分ける。

`category` は侵される対象を表し、`failure_injection`、`temporal`、`shape`、
`value`、`state` の5値に閉じる。`severity` は観測形態を表し、`error`、
`silent_corruption`、`delay` の3値に閉じる。新しい障害名は「犬の行動 ×
1語で結果形状が想像できる」ものとし、追加時には上表と実装の一次対応表へ
`category`、`severity`、rowcount可視性を同時に登録しなければならない。

`max_intervention_rows`（既定 10,000）は materialize 済み結果に `on_result` fault を適用する行数上限であり、取得件数または保持メモリの上限ではない。超過結果を切り詰めてはならない。`on_max_rows="skip"`（既定）では結果を無改変で返し、`on_max_rows="error"` では `limit_exceeded` を記録した後に非 retryable な `DollyLimitError` を送出する。後者も backend 実行および全行 materialize の後に発生する「実行済みなのに例外」の意味論を持つ。

## イベント schema v2

イベントは1イベント1行の UTF-8 JSONL とする。全イベントに次のコアフィールドを必須とする。

| field | type | meaning |
|---|---|---|
| `schema_version` | integer | 常に `2` |
| `event_id` | string | 同じ replay で安定な一意識別子 |
| `session_id` | string | セッション識別子 |
| `seq` | integer | セッション内で1から欠番なく単調増加 |
| `event_type` | string | 下表のイベント種別 |

イベント種別ごとの追加必須フィールドは次のとおりである。

| event_type | required fields beyond core |
|---|---|
| `fault_injected` | `fault`, `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details` |
| `treasure_returned` | `fault`, `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details` |
| `mood_changed` | `details`（`from`, `to`, `tick`） |
| `limit_exceeded` | `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details`（`limit`, `configured`, `observed`） |
| `decision_evaluated` | `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details` |

`fault_injected` と `treasure_returned` は `schema_version` を除いてv1と同じ必須フィールド集合を持つ。未定義の拡張フィールド、診断用 timestamp、任意の `mood` は replay 比較の対象外とする。writer は単一プロセス・単一インスタンス契約である。reader はv1とv2の混在を受理し、未知の schema version、不正JSON、不正UTF-8、必須フィールド不足の行を警告付きでスキップする。

`fault_injected` は任意フィールドとして `category` と `severity` を持つ。
両フィールドは必須フィールド集合および replay 比較には含めず、
`schema_version` は2のままとする。`treasure_returned`、`mood_changed`、
`limit_exceeded`、`decision_evaluated` には両フィールドを記録しない。

### warning outcome 語彙

| event_type | outcome | meaning |
|---|---|---|
| `limit_exceeded` | `fault_skipped` | 介入上限を超えたため結果を無改変で返し、fault 注入を見送った |
| `limit_exceeded` | `error` | 介入上限を超えたイベントを記録後、`DollyLimitError` を送出した |
| `decision_evaluated` | `not_injected` | debug 評価では候補を調べたが fault は適用されなかった |

`limit_exceeded.details.limit` は現在 `max_intervention_rows`、`configured` は設定上限、`observed` は materialize された行数である。旧識別子 `max_rows` は、本変更（`max-rows-and-session-limits`）適用前に記録された履歴イベントにのみ出現する。生SQL、生パラメータ、生行値をイベントへ含めてはならない。

## native passthrough と escape hatch 統計

接続proxyの未定義属性は既定で生接続へ転送せず、`AttributeError`で拒否する。`allow_native_passthrough=True`を明示した場合だけ転送を許可し、callableな属性が実際に呼ばれた時点で`stats()["escape_hatches"]`を増分する。アダプタが宣言したSQL実行能力のある入口は属性名ごとに、それ以外のcallableは`other`に集約する。属性取得や`hasattr`だけでは増分しない。また、生SQL、生パラメータ、呼び出し引数は統計に保持しない。

escape hatchの値はnative methodの**呼び出し回数**であり、backendが実行したSQL数ではない。とくにDuckDBの`sql()`は遅延評価されるrelationを返すため、`sql`の呼び出し回数と実際のSQL実行回数は一致するとは限らない。転送経路は障害注入、イベント記録、論理時計、occurrence更新の対象外である。

## バックエンド別公開表面と適合契約

公開表面はバックエンドごとに分岐し、宣言した対応表面内でそれぞれのネイティブ接続と同型でなければならない。両バックエンド間で一致を要求する conformance 契約は介入コアに限定する。同一 seed・同一 SQL 列に対する decision、障害イベント列、および論理結果への障害適用結果は一致しなければならないが、execute の返り値型、結果取得の入口、コンテキストマネージャ意味論を含む公開表面の一致は要求しない。表面挙動は「もう一方のバックエンド」ではなく、各バックエンドのネイティブドライバ（sqlite3／duckdb）との同型性で検証する。クロスバックエンドの表面等価性は契約の対象外である。

### SQLite 表面

`execute()` および `executemany()` は sqlite3 の接続ショートカットと同型に、呼び出すたびに新規の `CursorProxy` を返す。返り値は接続自身でも過去のカーソルでもなく、各カーソルが独立した結果状態と消費位置を持つ。`cursor()` は未実行の `CursorProxy` を返し、その `execute()` は介入コアを経由してカーソル自身を返す。

接続レベルの `fetchall`／`fetchone`／`fetchmany`／`description`／`rowcount` は提供しない。これらへアクセスした場合は、`execute()` が返したカーソルを使うよう案内するメッセージ付きの `AttributeError` を送出する。

`with conn:` はトランザクションだけを管理する。例外なしで抜けた場合は commit、例外で抜けた場合は rollback し、どちらの場合も接続を close しない。

### DuckDB 表面

`execute()` は接続自身を返し、接続レベルの `fetchall`／`fetchone`／`fetchmany`／`description`／`rowcount` を提供する。`description` は、障害適用後の列名と DuckDB ネイティブの第2スロットの型情報から `(name, type, None, None, None, None, None)` を再構成する。型情報は正規化せず、TANGLED_LEASH で列名が入れ替わっても値を記述する列位置に留める。

`cursor()` はネイティブのクローン接続を同型の `DuckDBProxy` で包んで返し、クローンの `cursor()` も再帰的に同様に包む。親子は介入コアを共有するため、decision・occurrence・イベント・stats・house・論理時計は全クローン横断で合算される。一方、SQL の実行先、トランザクション文脈、`close()`／`__exit__` の対象は各ネイティブ接続に属する。親子・クローン間のトランザクション分離は DuckDB ネイティブと同型であり、DogDB は変更・管理・検出しない。クローンを閉じても共有介入コアには影響しない。`with conn:` は終了時にその接続を close する。

遅延評価 relation を返す `sql()`／`query`／`table` は宣言した介入表面外であり、既定では誘導付きの `AttributeError` で fail-closed とする。

### 明示的不忠実

`row_factory` は SQLite／DuckDB のどちらの表面でも対応しない。DogDB は行を tuple に正規化する。これは障害適用の決定性を行表現に依存させないために、ADR-001 の優先順位「決定性 ＞ 宣言表面の忠実性」を適用した明示的不忠実であり、対応漏れではない。

## 破壊的変更と移行

SQLite 表面では、`execute()`／`executemany()` の返り値が接続自身から毎回新規の `CursorProxy` へ変わり、接続レベルの結果取得を廃止した。また、`__exit__` は無条件 close から commit／rollback のトランザクション管理へ変わり、接続を close しなくなった。conformance 契約はクロスバックエンドの表面等価性から介入コアの一致へ縮小した。DuckDB 表面にこれらの変更はない。

`conn.execute(sql).fetchall()`、`fetchone()`、`fetchmany()` の連鎖形は、旧表面（`execute()` が接続自身を返す）と新しい SQLite 表面（カーソルを返す）の両方で動作するため、今後の推奨形とする。`conn.execute(sql)` の後で `conn.fetchall()`／`conn.description`／`conn.rowcount` を接続へ直接呼び出すコードは、返されたカーソルを保持して結果を取得する形へ書き換える。

```python
cursor = conn.execute("select * from treats")
rows = cursor.fetchall()
description = cursor.description
rowcount = cursor.rowcount
```

`with conn:` の終了時 close に依存するコードは、ブロック後に `conn.close()` を明示的に呼び出す。SQLite では `with` が接続寿命を管理しないため、必要に応じて `try`／`finally` または `contextlib.closing` で close を保証する。

## SQL、scope、backend の境界

core は backend ライブラリを import してはならず、backend 由来の例外を変換してはならない。DogDB はSQLを書き換えず、分類済み操作の論理結果だけを加工する。SQL 分類は sqlglot による構文解析を用いる。

`only_tables` / `exclude_tables` は保守的に抽出できたトップレベル `FROM` のテーブル名へ適用する。抽出不能文は `only_tables` 指定時は対象外、`exclude_tables` 指定時は対象とする。両方のscopeを同時に指定してはならない。scope、イベント、統計へ生SQLや生パラメータを保持してはならない。
