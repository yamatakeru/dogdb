# DogDB contract v1

> **歴史的文書:** policy v4 以降では本書の決定値互換性は失効している。ワイヤスキーマ規則は event-log spec を参照すること。

この文書は実装言語、DB ドライバ、将来の proxy 形態に依存しない DogDB v1 の相互運用契約である。キーワード MUST / MUST NOT / SHALL は拘束要件を表す。

## 決定関数

UTF-8 文字列を NUL（`0x00`）で連結し、次を計算する。

```text
decision_key = "sha256:" + hex(SHA-256(
  policy_version, seed, session_id,
  template_fingerprint, decimal(occurrence), phase
))
```

`policy_version` は `dogdb-v1:normalize=trim+collapse-whitespace+lowercase`、`phase` は `before_execute` または `on_result` である。同一 template fingerprint の occurrence はセッション内で 1 から始まり、実行ごとに1増える。wall-clock、OS 乱数、言語固有の非安定 hash は決定へ使用してはならない。

既定ではパラメータ fingerprint は決定キーに含めない。`include_params=true` の場合のみ、上記の末尾へ `parameter_fingerprint` をもう1要素として連結する。

確率判定、行位置、順列も decision key を入力とする SHA-256 から導出しなければならず、外部乱数を使ってはならない。1操作では failure injection（IGNORE、STASH error）を silent mutation（STASH missing、SHUFFLE）より優先し、最大1 fault だけを適用する。

## fingerprint 正規化

SQL template の v1 正規化は次の順序で行う。

1. 先頭末尾の Unicode whitespace を除去する。
2. 連続する whitespace を単一の ASCII space に置換する。
3. Unicode の lowercase 変換を行う。
4. UTF-8 bytes の SHA-256 を取り、`sha256:<lowercase hex>` とする。

これは SQL 構文正規化ではない。コメント、リテラル、placeholder 方言は書き換えない。

位置パラメータは順序を保つ JSON array として、空白なし・UTF-8 で直列化する。JSON ネイティブでない値は `{ "type": fully-qualified-type, "value": string-value }` とする。`string-value` は値の安定した正規テキスト表現でなければならず（MUST）、オブジェクト識別子（メモリアドレス等）に依存する表現しか得られない値は直列化を拒否しエラーとしなければならない（MUST）。`type` タグは実装内部の型名であり、クロス言語での一致は保証しない。セッション固有鍵による HMAC-SHA-256 を取り、`hmac-sha256:<lowercase hex>` とする。生パラメータをイベントへ記録してはならない。

## イベント schema v1

注入と返却は1イベント1行の UTF-8 JSONL とする。各イベントは次の全フィールドを必須とする。

| field | type | meaning |
|---|---|---|
| `schema_version` | integer | 常に `1` |
| `event_id` | string | 同じ replay で安定な一意識別子 |
| `session_id` | string | セッション識別子 |
| `seq` | integer | セッション内で1から欠番なく単調増加 |
| `event_type` | string | `fault_injected` / `treasure_returned` |
| `fault` | string/null | v1 は `STASH` / `SHUFFLE` / `IGNORE` |
| `phase` | string | `before_execute` / `on_result` / `manual_return` |
| `template_fingerprint` | string | 正規化 SQL の SHA-256 |
| `parameter_fingerprint` | string | HMAC 化したパラメータ識別子 |
| `occurrence` | integer | template のセッション内出現回数 |
| `decision_key` | string | 上記決定関数の出力 |
| `outcome` | string | 例: `not_executed`, `rows_hidden`, `rows_reordered` |
| `details` | object | fault 固有の非機密 metadata |

STASH の `details` は `row_indices` と `treasure_id` を持つ。生 SQL、生パラメータ、生行値を既定ログへ含めてはならない。timestamp を拡張フィールドとして持てるが replay 比較と決定には使わない。writer は単一プロセス・単一インスタンス契約とし、reader は破損 JSON 行を警告付きで飛ばして有効行を返す。

## house 意味論

treasure の同一性は `(template_fingerprint, zero-based result row index)` である。STASH 時に `treasure_id`、template fingerprint、行位置、行値、発生 event ID をメモリへ保持する。同じ location は二重登録しない。同じ template の再実行では返却まで同じ位置を隠す。

`return_treasure(id)` は指定 treasure、`return_all()` は全 treasure の隠し状態を解除し、各解除を `treasure_returned` として記録する。返却は実テーブルへの行挿入ではない。

ログ射影は空集合から開始し、`fault_injected` の STASH で treasure ID を追加し、`treasure_returned` で削除する。この射影の未返却 ID 集合は live house と常に一致しなければならない。行値はログにないため、ログ単独から再構築する射影は identity と隠し状態を対象とする。

## SQL と backend の境界

STASH / SHUFFLE は明確に分類できた SELECT のみ対象とし、SHUFFLE はトップレベル ORDER BY がない場合だけ適用する。CTE、複文、PRAGMA 等の分類不能文、名前付きパラメータ、`executemany` は無介入で backend へ渡す。IGNORE は分類済み操作の実行前に送出し、`outcome="not_executed"`、`retryable=true` とする。

backend adapter は `execute -> {columns, rows, rowcount}`、`close`、`in_transaction` を提供する。core は backend ライブラリを import してはならず、実 DB 例外を変換してはならない。
