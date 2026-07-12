# backend-faithful-surfaces — タスク

## 1. 介入エンジンの抽出

- [ ] 1.1 `DBAPIProxy` から介入パイプライン（SQL分類・decision・アダプタ実行・障害適用・イベント/統計/house/論理時計）を内部エンジンクラスとして抽出する（表面と結果状態を持たない）
- [ ] 1.2 `dolly` 名前空間をエンジン参照に付け替え、両表面で共有できるようにする
- [ ] 1.3 検証: 既存テストスイート（`pytest`）を、この時点では表面無変更のまま全通過させる（エンジン抽出単独での回帰ゼロを確認）

## 2. DuckDB表面

- [ ] 2.1 現行表面（execute が自身を返す・接続レベル fetch*・`__exit__`=close・fail-closed 機構）を `DuckDBProxy` として位置づけ、`wrap()` がアダプタ判別でプロキシクラスを選択するようにする

## 3. SQLite表面

- [ ] 3.1 `CursorProxy` を実装する: `execute`（エンジン経由・自身を返す）／`fetchall`・`fetchone`・`fetchmany`／`__iter__`／`description`／`rowcount`、materialize 済み結果とカーソルごとの消費位置（`__iter__` と `fetch*` は共有）
- [ ] 3.2 `SQLiteProxy` を実装する: `execute`／`executemany` は毎回新規 `CursorProxy` を返す、`cursor()` は未実行 `CursorProxy` を返す（fail-closed 解除）、接続レベルの結果取得（fetch*／description／rowcount）は提供しない
- [ ] 3.3 `SQLiteProxy.__exit__` を「例外なしなら commit・例外時 rollback・close しない」に実装する
- [ ] 3.4 fail-closed 誘導メッセージをバックエンド別公開表面に整合させる（SQLite: `executescript` 等は誘導付き拒否のまま、`cursor` は開通）

## 4. テスト

- [ ] 4.1 既存テスト・examples の表面依存箇所を更新する（`conn.fetchall()` 形→`conn.execute(sql).fetchall()` 連鎖形、close 依存の `with`→明示 close）
- [ ] 4.2 SQLite表面のユニットテストを追加する: execute 返り値の独立性（踏み潰しなし）、cursor()≡execute ショートカット同型、イテレーションと fetch の消費位置共有、`with` の commit/rollback/非close
- [ ] 4.3 ネイティブ並走テストを追加する: 同一操作列を素の sqlite3 と全障害確率0の SQLiteProxy に流し、表面挙動（返り値構造・行・description・rowcount・トランザクション状態）の一致を機械検証する
- [ ] 4.4 conformance テストを「介入コア一致」に書き換える: 表面分岐下（DuckDB=接続fetch、SQLite=カーソルfetch）で同一seed・同一SQL列の障害イベント列・論理結果一致を検証する
- [ ] 4.5 cursor() 経由と execute() 経由で decision・イベント列が一致することを検証するテストを追加する
- [ ] 4.6 検証: `pytest` 全通過、`openspec validate backend-faithful-surfaces` 通過

## 5. ドキュメント

- [ ] 5.1 `docs/contract-v2.md` と README の表面契約記述をバックエンド別表面に更新する（SQLite の execute 返り値・with 意味論・接続レベル fetch の廃止、DuckDB は現行維持、row_factory の明示的不忠実）
- [ ] 5.2 破壊的変更点（execute 返り値・`__exit__` 意味論・conformance 契約の縮小）と移行方法（`execute(...).fetchall()` 連鎖形）を契約文書に明記する

## 6. GitHub連携

- [ ] 6.1 issue #6 に完了コメントを投稿し、クローズする（mainマージ後）
- [ ] 6.2 統括 issue #11 のチェックボックス（W2）を更新する
