# Dolly's First Shift

`Dolly's Treat Delivery` は、DogDBがアプリケーションの暗黙のSQL順序依存を見つける過程をWeb UIで体験するチュートリアルです。

ドリーはデータベースを壊しません。SQLiteが正常に返した行をアプリケーションへ届ける途中で、順番を変えるだけです。クエリは成功するため、アプリケーションが返却順を誤って信用していると、顧客には古い注文状態が表示されます。

## 公開デモ

[Cloudflare上の公開デモ](https://dogdb-dolly-demo-spike.yamato-y.workers.dev)は、サーバー処理を必要としないStatic Assetsとして無料配信しています。表示する結果は固定のサンプルデータではなく、デプロイのビルド時に実際のDogDBとin-memory SQLiteで[`scenario.py`](scenario.py)を実行して生成したtraceです。

公開版ではボタンを押した時点でDogDBを再実行せず、ビルド済みのtraceを読み込んで同じ画面を再生します。クリックごとのDogDB実行を確認する場合は、次のローカル版を利用してください。ローカル版と公開版は、シナリオ実装、レスポンス形式、HTML、CSS、JavaScriptを共有しています。

## ローカル実行

リポジトリのルートで次を実行します。

```console
uv run python -m examples.dollys_treat_delivery
```

ブラウザで <http://127.0.0.1:8000> を開き、3つの幕を順番に実行してください。外部のCDN、フォント、JavaScriptは利用しないため、起動後はオフラインで動作します。

## 3つの幕

| 幕 | DogDB設定 | SQL | 結果 |
|---|---|---|---|
| Normal route | `faults={}` | `ORDER BY`なし | SQLiteの返却順が偶然時系列と一致し、テストは通る |
| Dolly clocks in | `faults={"SHUFFLE": 1.0}` | 同じSQL | 行順だけが変わり、顧客画面の状態が過去へ戻る |
| Fix the manifest | SHUFFLEは有効なまま | `ORDER BY sequence`を追加 | SHUFFLEの候補外となり、正しい最新状態を表示する |

バグのあるクエリは、返却された最後の行を最新イベントだと思い込みます。

```sql
select sequence, status
from order_events
where order_id = ?
```

修正版は、アプリケーションが必要とする順序をSQLで明示します。

```sql
select sequence, status
from order_events
where order_id = ?
order by sequence
```

重要なのは、最後の幕でもSHUFFLEを無効化していないことです。DogDBのSQL分類器がトップレベルの`ORDER BY`を認識し、順序を宣言したSELECTをSHUFFLEの候補から外します。

## 実データによる演出

Web UIのカード順、顧客向け状態、Incident reportは、すべて`scenario.py`が実行したSQLiteの結果と`conn.dolly.log()`から生成します。画面表示のためにSHUFFLE結果を別途作ってはいません。ローカル版はクリック時に生成し、公開版はデプロイのビルド時に生成します。

各幕は新しいin-memory SQLite接続から開始し、同じ`seed=42`と`session_id="dolly-first-shift"`を使います。そのためブラウザで何度実行しても、SHUFFLE幕では同じ返却順と同じイベントIDを再現します。

## 構成

```text
Browser
  -> GET /api/acts/<act>.json
  -> local: fresh SQLite database -> dogdb.wrap(...)
  -> hosted: build-generated JSON from the same scenario
  -> application reads the last delivered row
  -> actual rows and DogDB events returned as JSON
  -> browser animates that trace
```

Flaskはローカル表示と固定シナリオAPIだけを担当します。任意SQL、任意fault、ファイル書き込み、外部ネットワークアクセスは提供しません。サーバーは`127.0.0.1`にのみbindし、本番利用を想定していません。

## テスト

デモ固有のシナリオ、API、HTML shell、画像配信は通常のテストスイートに含まれます。

```console
uv run pytest tests/test_treat_delivery_demo.py
```

より短いSHUFFLEのコード例は[`../02_shuffle_ordering_bug.py`](../02_shuffle_ordering_bug.py)を参照してください。
