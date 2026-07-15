# DogDB

> Sometimes your data has gone to the doghouse.

DogDB は DuckDB / SQLite の DB-API 接続を包み、SQL の意味論レベルで再現可能な障害を注入するテスト専用ツールです。犬のドリーが行をハウスへ持ち去ったり、値や形を変えたり、応答を渡さなかったりします。同じseed・session・設定・入力列なら同じ障害を再現できます。

<p align="center"><img src="docs/assets/dolly.png" alt="ゴミ箱の蓋から首が抜けなくなったドリー" width="380"></p>
<p align="center"><em>ゴミ箱の蓋から首が抜けなくなったドリー。悪気はない。DogDB が注入する障害にも、悪気はない。</em></p>

## クイックスタート

通常インストールではDuckDBドライバに加えて、方言中立なSQL分類に使うsqlglotが依存として導入されます。SQLiteバックエンド自体はPython標準の`sqlite3`を使います。

```python
import duckdb
import dogdb

raw = duckdb.connect(":memory:")
raw.sql("create table treats(id integer, name varchar)")
raw.sql("insert into treats values (1, 'bone'), (2, 'ball'), (3, 'rope')")

conn = dogdb.wrap(
    raw,
    seed=42,
    # 最初は1障害だけから始める。
    faults={"STASH": 0.25},
)
rows = conn.execute("select * from treats").fetchall()
print(conn.dolly.log())
print(conn.dolly.house())
conn.dolly.return_all()
```

SQLite なら `dogdb.connect("test.sqlite", backend="sqlite", seed=42)`、DuckDB なら `backend="duckdb"` を使えます。`seed` は必須です。既定の障害確率はすべて0で、`faults`または`fault_probabilities`に障害名と0〜1の確率を渡します。まず1障害を小さな確率で有効化し、テストが安定してから次の障害を1個ずつ足してください。

イベントを JSONL に残すには `log_path="dogdb-events.jsonl"` を指定します。生 SQL、生パラメータ、生行値は記録されません。パラメータを決定キーにも参加させたい場合だけ `include_params=True` を指定してください。

## バックエンド別の接続表面

DogDB は介入コアを共有しますが、接続表面は各ネイティブドライバに合わせて分岐します。conformance が保証するのは、同一seed・同一SQL列に対する decision、障害イベント列、論理結果への障害適用結果という「介入コアの一致」です。SQLite と DuckDB の公開表面が互いに同じであることは保証せず、宣言した対応表面内でそれぞれ sqlite3／duckdb と同型になるよう検証します。クロスバックエンドの表面等価性は対象外です。

### SQLite

`execute()` と `executemany()` は、sqlite3 のショートカットメソッドと同じく、呼び出すたびに新規の `CursorProxy` を返します。各カーソルの結果と消費位置は独立しています。`cursor()` は未実行の `CursorProxy` を返します。

接続自身には `fetchall`／`fetchone`／`fetchmany`／`description`／`rowcount` がありません。アクセスすると、`execute()` が返したカーソルを使うよう案内する `AttributeError` になります。`with conn:` は例外なしならcommit、例外時はrollbackするトランザクション管理であり、接続はcloseしません。

### DuckDB

`execute()` は接続自身を返し、接続レベルの `fetchall`／`fetchone`／`fetchmany`／`description`／`rowcount` を利用できます。`description` は、障害適用後の列名と DuckDB ネイティブの型情報（第2スロット、無変換）から再構成されます。TANGLED_LEASH で列名が入れ替わっても、型情報は値の列位置に留まります。`cursor()` は DuckDB ネイティブのクローン接続を新しい `DuckDBProxy` で包んで返し、クローンの `cursor()` も同様です。親子は decision・イベント・stats・house・論理時計を共有し、セッションは全クローン横断の `execute()` 呼び出し順として扱われます。一方、各クローンのトランザクション分離と close の対象は DuckDB ネイティブと同じであり、DogDB は変更しません。`with conn:` は終了時にその接続をcloseします。遅延評価 relation を返す `sql()`／`query`／`table` は引き続き fail-closed で、`execute()` または `allow_native_passthrough=True` を案内する `AttributeError` を送出します。

### 明示的不忠実

`row_factory` はどちらのバックエンドでも対応しません。行をtupleに正規化し、障害適用の決定性を行表現に依存させないためです。これは優先順位「決定性 ＞ 宣言表面の忠実性」を適用した明示的不忠実であり、対応漏れではありません。

### 破壊的変更と移行

SQLite では、`execute()` の返り値が接続自身から毎回新規のカーソルへ変わり、`__exit__` は無条件closeからcommit／rollbackへ変わりました。また、conformance 契約はクロスバックエンドの表面等価性から介入コアの一致へ縮小しました。

`conn.execute(sql).fetchall()` のような連鎖形は旧表面と新表面の両方で動くため、今後の推奨形です。`conn.execute(sql)` の後で `conn.fetchall()`／`conn.description`／`conn.rowcount` を接続へ直接呼び出していたコードは、返されたカーソルを使う形へ変更してください。

```python
cursor = conn.execute("select * from treats")
rows = cursor.fetchall()
description = cursor.description
rowcount = cursor.rowcount
```

`with conn:` が接続をcloseすることに依存していたコードは、SQLite ではブロック後に `conn.close()` を明示的に呼び出してください。

## 障害モデル

| DogDB の障害 | 振る舞い | 対応する実在障害クラス |
|---|---|---|
| STASH（行欠落） | SELECT 結果の1行を返却まで隠す | 一時的な結果欠落、replica の可視性遅延 |
| STASH（エラー） | 結果取得時に構造化例外 | 部分読み取り・取得失敗 |
| SHUFFLE | ORDER BY のない SELECT を決定的に並べ替える | 暗黙順序への依存、実行計画差 |
| IGNORE | 実行前にリトライ可能例外を送出 | lost request、接続 timeout |
| ECHO | 1行を直後に複製 | duplicate delivery |
| TAIL_CHASE | 結果末尾を切り詰める、または部分読取りエラー | premature EOF |
| FALSE_EMPTY | 列を保った0行結果を返す | false negative read |
| PAGE_HOLE | OFFSETページの先頭側を欠落させる | pagination hole |
| CHEW | 閉じたprofileで1セルを破損 | encoding／precision corruption |
| TANGLED_LEASH | 隣接する列labelだけを交換 | column-label drift |
| WRONG_COUNT | logical rowcountだけを改変 | ack-count mismatch |
| SLOTH | 決定的な遅延後に実行を続ける | slow query |
| BARK | 実行前に`DollyBarkError` | transient connection error |
| GUARD_BOWL | 実行前に`DollyBusyError` | lock timeout／database busy |
| NO_DROP | SELECT実行後に`DollyNoDropError` | lost response |
| OLD_BONE | 同じfingerprintの過去の配達結果を返す | stale replica read |
| 手動 RETURN | house の隠し状態を解除する | replica の追随、可視性回復 |
| 自動 RETURN | 論理操作数の経過後に宝物を返す | eventual consistency |

注入例外は `DogDBError` の派生型で、`event_id`、`fault`、`phase`、`retryable`、`outcome` に加え、読み取り専用の `category` と `severity` を持ちます。バックエンド固有の実エラーはラップしません。イベントログも同じ分類属性を持つため、たとえばサイレント破損だけをテストで抽出できます。

```python
silent_corruptions = [
    event
    for event in conn.dolly.log()
    if event.severity == "silent_corruption"
]
assert all(event.category in {"shape", "value", "state"} for event in silent_corruptions)
```

### opt-in状態機能

```python
conn = dogdb.wrap(
    raw,
    seed=42,
    faults={"STASH": 0.1, "OLD_BONE": 0.1},
    mood={"epoch_length": 10},
    auto_return={"min_operations": 2, "max_operations": 5},
)
```

`mood`はCALM／SLEEPY／ZOOMYを論理時計で遷移し、faultの実効weightだけを変えます。`auto_return`はSTASHの宝物を決定的な操作数の後に返します。`OLD_BONE`を有効化したセッションだけが、fingerprintごと4件・全体64件の配達済み結果cacheを持ちます。

SLOTHを待たずにテストするにはsleep互換のno-op clockを注入します。

```python
observed = []
conn = dogdb.wrap(
    raw,
    seed=42,
    faults={"SLOTH": 1.0},
    clock=observed.append,
)
conn.execute("select 1").fetchall()
assert observed[0] > 0
assert conn.dolly.log()[0].details["delay_ms"] > 0
```

`conn.dolly.stats()`は匿名fingerprintごとのSELECT／UNKNOWN分類数と介入数に加え、理由別の匿名素通し件数（`passthrough`）と、`allow_native_passthrough=True`時のネイティブ転送呼び出し回数（`escape_hatches`、属性の取得時ではなく呼び出し時に集計）を返します。診断メタ情報として`sqlglot_version`も返しますが、decision keyやイベントschemaには使いません。生SQL、生parameter、parameterの型名は含みません。

`passthrough` は発生した理由だけを含む疎な辞書です。理由キーの正規語彙は次の5種です。

| 理由キー | 発生箇所 |
|---|---|
| `named_parameters` | Mapping型の名前付きパラメータを使う`execute` |
| `unknown_sql` | SQL分類器がUNKNOWNと判定した文 |
| `transaction_statement` | BEGIN／COMMIT／ROLLBACK |
| `unsupported_parameter_type` | fingerprint入力域外の位置パラメータを使う`execute` |
| `executemany` | `executemany`入口 |

`wrap(..., on_passthrough=...)` で素通しの扱いを選べます。既定の`"allow"`は静かに実行を続け、`"warn"`は`DollyPassthroughWarning`を通知してから実行を続け、`"error"`は`DollyPassthroughError`（`retryable=False`）でバックエンド実行前に止めます。warn/errorの発火対象は`named_parameters`、`unknown_sql`、`unsupported_parameter_type`です。正常運転上必要な`transaction_statement`と、明示的に対象外の`executemany`は、どのモードでも無警告・無エラーで素通しします。理由別のstats記録はモードに関わらず行われます。

## 使用例

- [STASH と house](examples/01_stash_and_house.py) — 隠れた行の粘着性と `return_all()` による復帰を確認します。
- [SHUFFLE と暗黙順序のバグ](examples/02_shuffle_ordering_bug.py) — `ORDER BY` の有無による集計結果の違いを比較します。
- [IGNORE の再試行](examples/03_ignore_retry.py) — `retryable` を見て安全に再試行するパターンを示します。
- [pytest でのカオステスト](examples/04_pytest_chaos.py) — フィクスチャとイベントログの assert で耐障害性を検証します。
- [障害を1個ずつ追加](examples/05_add_faults_one_at_a_time.py) — ECHOとno-op clock付きSLOTHを別セッションで試します。
- [mood・自動返却・OLD_BONE](examples/06_stateful_faults.py) — 状態系opt-inと匿名statsを確認します。

## 限界と安全上の前提

- 決定性の保証単位はセッション全体です。同一 seed・session・設定・sqlglotバージョンで、セッション先頭から同一の順序付き操作列を流した場合のみ同じ障害列を再現し、途中からの部分 replay や異なるsqlglotバージョン間の一致は保証しません。
- 対応する入口は上記のバックエンド別接続表面に限定します。それ以外の未知属性は、障害注入を沈黙のまま迂回させないため既定で拒否します。生接続の機能が必要な場合は`allow_native_passthrough=True`を`wrap()`へ指定できますが、その転送経路は障害注入・イベント記録・論理時計・occurrence更新の対象外です。
- 行同一性は主キーではなく、結果セット内の位置です。パラメータや元の順序が変わると同じ位置が別の行を指す場合があります。
- SQL 分類は全バックエンドでsqlglotの方言中立（generic）parseを使います。CTE（`WITH ... SELECT`）とUNION／EXCEPT／INTERSECTはSELECTとして障害候補になります。`INSERT`／`UPDATE ... RETURNING`はOTHERのままで、複文、PRAGMA、EXPLAIN、parse失敗・分類不能文、名前付きパラメータ、fingerprint入力域外の位置パラメータ、`executemany`へ直接faultは注入せず、faultのdecision／event／occurrenceを生成しないまま素通しします。これらの素通し操作でもmood／自動返却の論理時計は1操作として進むため、mood遷移や自動返却（`auto_return`）の状態イベントは生成され得ます。
- 「注入したつもり」の素通しを明示的に検出するには`on_passthrough="warn"`または`"error"`を指定します。`transaction_statement`と`executemany`は通知・拒否の対象外です。
- 結果を `execute` 時に全件 materialize します。`max_intervention_rows`（既定 10,000）は materialize 済み結果へ fault を適用する行数上限であり、取得件数や保持メモリの上限ではありません。超過時も既定では全行を無改変で返すため、メモリ保護にはなりません。house は 1,000 件を上限とし、小規模なテストデータを前提にします。
- 大きすぎる結果を明示的にテスト失敗にするには `on_max_rows="error"` を指定します。`limit_exceeded` を記録してから非 retryable な `DollyLimitError` を送出しますが、この判定はバックエンド実行と全行 materialize の後です。必要なら `max_intervention_rows` を調整してください。
- occurrence カウンタと fingerprint 単位の統計は、決定性を守るためセッション中に退避・再初期化せず単調増加します。長時間稼働プロセスへ常設せず、テストケースまたは小規模テストスイート単位で接続をラップし直してください。
- JSONL は単一 writer 契約です。複数プロセスから同じファイルへ追記しないでください。
- 本番向けの信頼性機構ではなく、テスト専用のカオスツールです。

言語中立の現行契約は[docs/contract-v2.md](docs/contract-v2.md)、履歴契約は[docs/contract-v1.md](docs/contract-v1.md)を参照してください。書き込み後の応答喪失を実装しない理由は[orphan write調査](docs/orphan-write-investigation.md)にまとめています。
