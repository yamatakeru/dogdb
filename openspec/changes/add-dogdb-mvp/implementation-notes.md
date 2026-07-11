# Implementation notes: add-dogdb-mvp

## SQL 分類器の実介入率

依存を増やさず安全側へ倒すため、quote・line/block comment・括弧深度だけを走査する小さな lexer とした。代表12文（単純 SELECT、ORDER BY、subquery、comment 付き SELECT、INSERT、UPDATE、BEGIN、CREATE、CTE、PRAGMA、EXPLAIN、複文）では8文を分類でき、分類率は 66.7% だった。read-like 6文のうち介入可能な SELECT は4文（66.7%）。偽陽性を避ける狙いどおり CTE / PRAGMA / EXPLAIN / 複文は UNKNOWN になる。

`expand-dolly-faults` では実アプリの query corpus を匿名 fingerprint 単位で計測し、CTE が支配的なら parser 導入を再検討する。正規表現の追加で個別構文を追うより sqlglot 等の AST 境界が妥当である。

## DuckDB / SQLite adapter 差分

この環境ではネットワークが遮断され、実 DuckDB Python package を取得できなかったため、以下は DuckDB 公開 API に合わせた実装上の差分であり、実バイナリでの最終適合確認は保留である。

- SQLite の `execute` は cursor、DuckDB は connection 自体を返せるため、adapter は返却オブジェクトの `description` / `fetchall` だけを見る形へ揃えた。
- 両者とも SELECT の rowcount は互換な意味を持たないため、materialize 後の行数を logical rowcount とした。非 result 文は backend rowcount を保持する。
- `description` の各要素には backend 固有情報があるが、v1 は先頭の列名だけを保持する。
- SQLite は `in_transaction` を直接提供する。DuckDB は環境差を吸収するため未提供なら `False` とする。

core にはどちらの import もなく、adapter の実量はこの正規化に限定できた。後続では timezone、Decimal、大きな BLOB など値型の差を共通 suite に追加する価値がある。

## メモリ上限

v1 の既定は1結果 10,000 行、house 1,000 treasure とした。テスト用の数十〜数千行を十分覆い、誤って大きな分析 query を materialize したときの際限ない変換を避ける折衷である。ただし Python object の1行サイズは一定でないため、行数は厳密な byte 防御ではない。

`expand-dolly-faults` では `max_result_bytes` の概算計測、上限超過 warning event、streaming fault に必要な決定契約を検討する。長寿命セッションでは house の LRU 自動退避を入れず、明示 RETURN を維持する。

## schema v1 の運用感

timestamp を必須にしなかったことで replay の完全一致が簡単になった。注入例外とログを `event_id` で結べる点、`details` に treasure ID と位置だけを置いて行値を house に隔離する点も扱いやすい。

一方、RETURN にも全必須フィールドを埋めるため、元の occurrence / decision key / parameter fingerprint を treasure に保持する必要があった。これは監査には有用だが、イベント種別ごとの nullable 規則を次版で明文化したい。破損行 skip は JSONL の局所障害に効くが、単一 writer 制約は残る。後続では file rotation、session 混在時の seq 検証、warning event の共通 outcome 語彙を追加候補とする。
