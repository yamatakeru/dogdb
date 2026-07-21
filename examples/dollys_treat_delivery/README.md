# Dolly's First Shift

`Dolly's Treat Delivery` は、DogDBがアプリケーションの暗黙のSQL順序依存を見つける過程を、ローカルWeb UIで体験するチュートリアルです。

ドリーはデータベースを壊しません。SQLiteが正常に返した行をアプリケーションへ届ける途中で、順番を変えるだけです。クエリは成功するため、アプリケーションが返却順を誤って信用していると、顧客には古い注文状態が表示されます。

## 起動

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

Web UIのカード順、顧客向け状態、Incident reportは、すべて[`scenario.py`](scenario.py)が実行したSQLiteの結果と`conn.dolly.log()`から生成します。画面表示のためにSHUFFLE結果を別途作ってはいません。

各幕は新しいin-memory SQLite接続から開始し、同じ`seed=42`と`session_id="dolly-first-shift"`を使います。そのためブラウザで何度実行しても、SHUFFLE幕では同じ返却順と同じイベントIDを再現します。

## 構成

```text
Browser
  -> POST /api/acts/<act>
  -> fresh SQLite database
  -> dogdb.wrap(...)
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
