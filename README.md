# DogDB

> Sometimes your data has gone to the doghouse.

DogDB は DuckDB / SQLite の DB-API 接続を包み、SQL の意味論レベルで再現可能な障害を注入するテスト専用ツールです。犬のドリーが行をハウスへ持ち去ったり、値や形を変えたり、応答を渡さなかったりします。同じseed・session・設定・入力列なら同じ障害を再現できます。

<p align="center"><img src="docs/assets/dolly.png" alt="ゴミ箱の蓋から首が抜けなくなったドリー" width="380"></p>
<p align="center"><em>ゴミ箱の蓋から首が抜けなくなったドリー。悪気はない。DogDB が注入する障害にも、悪気はない。</em></p>

## クイックスタート

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

注入例外は `DogDBError` の派生型で、`event_id`、`fault`、`phase`、`retryable`、`outcome` を持ちます。バックエンド固有の実エラーはラップしません。

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

`conn.dolly.stats()`は匿名fingerprintごとのSELECT／UNKNOWN分類数と介入数に加え、理由別の匿名素通し件数（`passthrough`）と、`allow_native_passthrough=True`時のネイティブ転送呼び出し回数（`escape_hatches`、属性の取得時ではなく呼び出し時に集計）を返します。生SQL、生parameter、parameterの型名は含みません。

## 使用例

- [STASH と house](examples/01_stash_and_house.py) — 隠れた行の粘着性と `return_all()` による復帰を確認します。
- [SHUFFLE と暗黙順序のバグ](examples/02_shuffle_ordering_bug.py) — `ORDER BY` の有無による集計結果の違いを比較します。
- [IGNORE の再試行](examples/03_ignore_retry.py) — `retryable` を見て安全に再試行するパターンを示します。
- [pytest でのカオステスト](examples/04_pytest_chaos.py) — フィクスチャとイベントログの assert で耐障害性を検証します。
- [障害を1個ずつ追加](examples/05_add_faults_one_at_a_time.py) — ECHOとno-op clock付きSLOTHを別セッションで試します。
- [mood・自動返却・OLD_BONE](examples/06_stateful_faults.py) — 状態系opt-inと匿名statsを確認します。

## 限界と安全上の前提

- 接続proxyが対応する入口は`execute`、`executemany`、`fetchall`、`fetchone`、`fetchmany`、`description`、`rowcount`、`in_transaction`、`commit`、`rollback`、`close`、`dolly`、およびコンテキストマネージャです。それ以外の未知属性は、障害注入を沈黙のまま迂回させないため既定で拒否します。生接続の機能が必要な場合は`allow_native_passthrough=True`を`wrap()`へ指定できますが、その転送経路は障害注入・イベント記録・論理時計・occurrence更新の対象外です。
- 行同一性は主キーではなく、結果セット内の位置です。パラメータや元の順序が変わると同じ位置が別の行を指す場合があります。
- SQL 分類は意図的に保守的です。CTE、複文、PRAGMA、分類不能文、名前付きパラメータ、fingerprint入力域外の位置パラメータ、`executemany` へ直接faultは注入せず、faultのdecision／event／occurrenceを生成しないまま素通しします。これらの素通し操作でもmood／自動返却の論理時計は1操作として進むため、mood遷移や自動返却（`auto_return`）の状態イベントは生成され得ます。
- 結果を `execute` 時に全件 materialize します。`max_intervention_rows`（既定 10,000）は materialize 済み結果へ fault を適用する行数上限であり、取得件数や保持メモリの上限ではありません。超過時も既定では全行を無改変で返すため、メモリ保護にはなりません。house は 1,000 件を上限とし、小規模なテストデータを前提にします。
- 大きすぎる結果を明示的にテスト失敗にするには `on_max_rows="error"` を指定します。`limit_exceeded` を記録してから非 retryable な `DollyLimitError` を送出しますが、この判定はバックエンド実行と全行 materialize の後です。必要なら `max_intervention_rows` を調整してください。
- occurrence カウンタと fingerprint 単位の統計は、決定性を守るためセッション中に退避・再初期化せず単調増加します。長時間稼働プロセスへ常設せず、テストケースまたは小規模テストスイート単位で接続をラップし直してください。
- JSONL は単一 writer 契約です。複数プロセスから同じファイルへ追記しないでください。
- 本番向けの信頼性機構ではなく、テスト専用のカオスツールです。

言語中立の現行契約は[docs/contract-v2.md](docs/contract-v2.md)、履歴契約は[docs/contract-v1.md](docs/contract-v1.md)を参照してください。書き込み後の応答喪失を実装しない理由は[orphan write調査](docs/orphan-write-investigation.md)にまとめています。
