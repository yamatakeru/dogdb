# tasks — duckdb-cursor-clone-wrap

## 1. LogicalResultと型情報の透過（アダプタ層）

- [ ] 1.1 `core/models.py` の `LogicalResult` に省略可能な列型情報フィールドを追加する（design D3。core は不透明値として扱う）
- [ ] 1.2 `adapters/base.py` の `materialize()` で `description` 第2スロットを無変換で保存する（sqlite3 では None の列になる）
- [ ] 1.3 既存の `LogicalResult` 生成箇所（FALSE_EMPTY・OLD_BONE 等の障害変換を含む）を新フィールドと整合させ、TANGLED_LEASH で型が位置に留まること（design D4）を確認する

## 2. engine純化とDuckDBクローンの包み直し（プロキシ層）

- [ ] 2.1 `proxy/connection.py` の `_InterventionEngine` を介入コアの所有に純化し、実行先アダプタを表面から受け取る形へ整理する（design D1。SQLite経路の挙動は不変）
- [ ] 2.2 `DuckDBProxy.cursor()` を新設する: ネイティブ `cursor()` のクローン接続を新しいアダプタで包み、共有 engine で新しい `DuckDBProxy` を構築して返す（クローンの `cursor()` も再帰的に同様、design D2）
- [ ] 2.3 `DuckDBProxy.description` を `(name, type, None×5)` の再構成に変更する（design D6。SQLite 側 `CursorProxy.description` は不変）
- [ ] 2.4 クローンの `close()`/`__exit__` がクローン接続のみを閉じ、共有介入コアに影響しないことを確認する（design D8）

## 3. テスト

- [ ] 3.1 `test_native_passthrough.py` の `test_fail_closed_duckdb_cursor_does_not_reach_native_connection` を「cursor は包み直したプロキシを返す」検証へ置換する（`sql` の fail-closed テストは維持）
- [ ] 3.2 クローン横断の決定性テストを新設する: 同一SQL列を親のみ／親子交互で実行し decision・イベント列が一致する（合格ゲート）
- [ ] 3.3 クローン経由の STASH が親の `dolly.house()`/`dolly.log()` から見えるテスト、クローン close 後も共有コアが無事なテストを追加する
- [ ] 3.4 description 型透過の並走テストを新設する: 素の duckdb と全確率0プロキシで `description` が一致（型スロット含む）、sqlite3 側は `(name, None×6)` のまま一致（合格ゲート）
- [ ] 3.5 トランザクション分離の並走テストを追加する: 親の未コミットINSERTのクローンからの可視性が素の duckdb と一致する
- [ ] 3.6 `pytest` 全体を実行し、既存テストが無変更で通ること（3.1 の置換を除く）を確認する

## 4. 文書とチェック

- [ ] 4.1 `docs/contract-v2.md` を更新する: cursor の fail-closed 記述を包み直しへ、トランザクション分離の不関知、セッション＝全カーソル横断（stats・house・ログ合算が意図であること）、description 型透過を明記
- [ ] 4.2 `README.md` の該当記述（DuckDB 表面・cursor）を追随更新する
- [ ] 4.3 `openspec validate duckdb-cursor-clone-wrap` と pyright ベースライン（src/dogdb 6 errors 維持）を確認する

## 5. 完了処理（マージ後）

- [ ] 5.1 issue #9 へ完了コメントを投稿する（`Closes #9` により自動クローズ）
- [ ] 5.2 統括 issue #11 の W4-a チェックボックスを更新する
