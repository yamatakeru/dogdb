# NO_DROP書き込み拡張（orphan write）調査

## 結論

本changeではNO_DROPを書き込み文へ拡張しない。現行のNO_DROPは、分類済みSELECTをbackendで完了した後に`DollyNoDropError`を返す安全なlost-response障害として維持する。

書き込み後の応答喪失は実在する重要な障害だが、DB-API接続を包む現在の境界だけでは「書き込みが確定したのか」「transaction内でまだrollback可能なのか」「再試行してよいのか」をbackend横断で判定できない。誤った判定は、テスト対象が意図しない二重書き込みを起こすため、明示的な安全契約を先に設計すべきである。

## 想定する障害

orphan writeは次の順序を再現する。

1. backendがINSERT／UPDATE／DELETEを受理する。
2. 書き込みがcommitされる。
3. 成功応答だけが失われ、クライアントにはretryableに見えるエラーが返る。
4. クライアントが同じ操作を再試行すると、冪等性がなければ副作用が重複する。

これは実行前に失敗するIGNORE／BARK／GUARD_BOWLとは異なり、backend状態を変更する。SELECT限定NO_DROPより誤用時の影響が大きい。

## 安全に実装するための必須条件

### 明示opt-in

- `allow_orphan_writes=True`のような、通常のfault weightとは別の危険機能フラグを必須とする。
- 既定は恒久的に無効とする。
- 対象statementまたはtableのallowlistを必須とし、分類不能文へ適用しない。

### autocommit限定

- backend adapterが「当該statementの完了時点でcommit済み」を肯定的に証明できる場合だけ候補にする。
- 単に`in_transaction == False`であることをautocommitの証明として扱わない。backendやdriverによってtransaction開始・commitの観測点が異なるためである。
- adapter契約にautocommit状態とstatement後のcommit完了を表す能力を追加する必要がある。

### transaction内禁止

- 明示BEGIN後、savepoint内、暗黙transaction内では発火させない。
- transaction状態を判定できないadapterでは候補外とする。
- DogDBがcommitを代行してはならない。アプリケーションのtransaction境界を変更するためである。

### 事後観測手段

- テストは、エラー後に別接続から一意キー、operation ID、outbox行などを照会し、書き込み済みか確認できなければならない。
- 将来APIでは、ユーザーが純粋な観測callbackまたは検証queryを明示する設計が必要である。
- 生SQL、生parameter、取得行をイベントログへ残す方法で観測可能性を補ってはならない。

### 冪等性と再試行

- 注入例外の`retryable=True`は「同じ書き込みを無条件で再実行して安全」という意味にしてはならない。
- operation ID、一意制約、UPSERT、outbox／inboxなど、重複排除手段のあるテストだけを対象にする。
- エラー型には少なくとも`outcome="commit_unknown"`相当の機械可読状態が必要である。

## backend境界で不足している情報

現行adapter契約は`execute`、`close`、`in_transaction`とLogicalResultの正規化だけを提供する。orphan writeには次が不足している。

- statement種別を安全にINSERT／UPDATE／DELETEへ閉じる分類
- autocommitの有効状態
- statement完了後のcommit確定状態
- savepointを含むtransaction階層
- 別接続からの事後観測能力

SQLiteとDuckDBでこれらの公開表面とtransaction挙動は同一ではない。coreで推測せず、adapter capabilityとして肯定的に提供する必要がある。

## 将来changeの受け入れ条件

次の条件が揃った場合に限り、別changeとして再検討する。

1. adapterに`supports_orphan_write`とcommit確定能力を追加する。
2. 明示opt-in、対象allowlist、transaction内禁止を設定契約へ追加する。
3. `commit_unknown`専用例外とイベント語彙を定義する。
4. 別接続による事後観測をDuckDB／SQLite共通適合テストで検証する。
5. 冪等な再試行例と、非冪等操作を拒否する例を文書化する。

それまではSELECT限定NO_DROPが、lost responseを安全に再現できる境界である。
