# DogDB

> Sometimes your data has gone to the doghouse.

DogDB は DuckDB / SQLite の DB-API 接続を包み、SQL の意味論レベルで再現可能な障害を注入するテスト専用ツールです。犬のドリーが行をハウスへ持ち去ったり、並び順をかき回したり、リクエストを無視したりします。同じ seed・session・SQL 列なら同じ障害を再現できます。

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
    faults={"STASH": 0.25, "SHUFFLE": 0.25, "IGNORE": 0.05},
)
rows = conn.execute("select * from treats").fetchall()
print(conn.dolly.log())
print(conn.dolly.house())
conn.dolly.return_all()
```

SQLite なら `dogdb.connect("test.sqlite", backend="sqlite", seed=42)`、DuckDB なら `backend="duckdb"` を使えます。`seed` は必須です。既定の障害確率はすべて 0 で、`faults` または `fault_probabilities` に障害名と 0〜1 の確率を渡します。STASH は `stash_mode="missing"`（行欠落）または `stash_mode="error"`（`DollyStashedError`）です。

イベントを JSONL に残すには `log_path="dogdb-events.jsonl"` を指定します。生 SQL、生パラメータ、生行値は記録されません。パラメータを決定キーにも参加させたい場合だけ `include_params=True` を指定してください。

## 障害モデル

| DogDB の障害 | 振る舞い | 対応する実在障害クラス |
|---|---|---|
| STASH（行欠落） | SELECT 結果の1行を返却まで隠す | 一時的な結果欠落、replica の可視性遅延 |
| STASH（エラー） | 結果取得時に構造化例外 | 部分読み取り・取得失敗 |
| SHUFFLE | ORDER BY のない SELECT を決定的に並べ替える | 暗黙順序への依存、実行計画差 |
| IGNORE | 実行前にリトライ可能例外を送出 | lost request、接続 timeout |
| 手動 RETURN | house の隠し状態を解除する | replica の追随、可視性回復 |

注入例外は `DogDBError` の派生型で、`event_id`、`fault`、`phase`、`retryable`、`outcome` を持ちます。バックエンド固有の実エラーはラップしません。

## 限界と安全上の前提

- 行同一性は主キーではなく、結果セット内の位置です。パラメータや元の順序が変わると同じ位置が別の行を指す場合があります。
- SQL 分類は意図的に保守的です。CTE、複文、PRAGMA、分類不能文、名前付きパラメータ、`executemany` には介入しません。
- 結果を `execute` 時に全件 materialize します。既定上限は 10,000 行、house は 1,000 件で、小規模なテストデータを前提にします。
- JSONL は単一 writer 契約です。複数プロセスから同じファイルへ追記しないでください。
- 本番向けの信頼性機構ではなく、テスト専用のカオスツールです。

言語中立の詳細契約は [docs/contract-v1.md](docs/contract-v1.md) を参照してください。
