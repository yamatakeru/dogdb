## 1. 契約文書の確定（実装前の仕様源）

- [ ] 1.1 `docs/contract-v2.md`: fingerprint正規化規則をv4へ改訂する（リテラル保持・`''`エスケープ、コメント`--`/`/* */`除去、引用識別子lowercase維持、方言的クォーティング対象外の明記）
- [ ] 1.2 `docs/contract-v2.md`: 決定性の保証単位（「セッション先頭からの同一の順序付き入力列と同一設定」）に「分類器実装（sqlglot）のバージョン一致」を追加する
- [ ] 1.3 `docs/contract-v2.md`: `INSERT`/`UPDATE ... RETURNING`行への`on_result`介入を将来の拡張候補として非規範的に注記する（実装しない）
- [ ] 1.4 `docs/contract-v1.md`: 冒頭の歴史的文書マークをv4失効を含む記述へ更新する

## 2. 依存追加

- [ ] 2.1 `pyproject.toml`: `dependencies`にsqlglotを範囲制約（`>=採用版,<次メジャー`）で追加する
- [ ] 2.2 `uv.lock`を更新し、固定されたsqlglotバージョンを確認する

## 3. fingerprint正規化v4の実装

- [ ] 3.1 `src/dogdb/core/fingerprints.py`: `normalize_sql`を単一引用符リテラル保持＋コメント除去の新規則へ書き換える
- [ ] 3.2 単一引用符文字列の`''`エスケープを正しく認識し、リテラル境界判定がコメント認識より後に破綻しないことを実装で担保する（コメント認識をリテラル境界判定に先立って行う）
- [ ] 3.3 `--`行コメントおよび`/* */`ブロックコメントの除去を実装する
- [ ] 3.4 引用識別子（`"..."`）のlowercase維持が既存挙動から回帰していないことを確認する
- [ ] 3.5 テスト: `SELECT 'DOG'` / `SELECT 'dog'` が異なる`template_fingerprint`になることを検証する
- [ ] 3.6 テスト: リテラル内空白保持・`''`エスケープ・コメント内アポストロフィ（例: `-- don't`）の3ケースを検証する
- [ ] 3.7 テスト: コメント内容のみが異なるSQLが同一`template_fingerprint`になることを検証する

## 4. sqlglot分類器の実装

- [ ] 4.1 `src/dogdb/core/sql.py`: `classify_sql`をsqlglotベースへ全面置換する。全バックエンド共通の方言中立dialect（generic dialect）に固定する
- [ ] 4.2 CTE（`WITH ... SELECT`）をSELECT扱いに分類する
- [ ] 4.3 UNION/EXCEPT/INTERSECTをSELECT扱いに分類し、トップレベルORDER BY判定（SHUFFLE可否）を再実装する
- [ ] 4.4 `INSERT`/`UPDATE ... RETURNING`をOTHER維持で分類する（`on_result`介入は実装しない）
- [ ] 4.5 複文・PRAGMA・EXPLAIN・parse失敗/分類器が意味を判定できないASTノードをUNKNOWNへfall backする（例外を送出しない）
- [ ] 4.6 `_from_tables`相当（scope機能が使うトップレベルFROM/JOINテーブル名の保守的抽出）をsqlglot ASTから同一意味論で再実装する
- [ ] 4.7 `top_level_limit`/`top_level_offset`相当（PAGE_HOLE用、リテラルのみ受理）をsqlglot ASTから同一意味論で再実装する（`limit 5+5`のような式は不受理のまま維持）
- [ ] 4.8 テスト: CTE・UNIONへの介入（STASH・SHUFFLE等）テストを追加する
- [ ] 4.9 テスト: 複文・PRAGMA・parse失敗の素通し維持テストを追加する
- [ ] 4.10 テスト: 同一SQLをDuckDB/SQLite両セッションで分類し、分類結果（kind・tables・top_level_limit・top_level_offset・has_top_level_order_by）が一致することを検証する（dialect中立性）
- [ ] 4.11 design.mdのOpen Questionsに記載したCTE/UNIONのテーブル名抽出の具体的挙動（外側エイリアスのみ抽出するか抽出不能扱いにするか）を実装時に確定し、`tests/test_sql_scope.py`へ反映する

## 5. POLICY_VERSIONとstats()の更新

- [ ] 5.1 `src/dogdb/core/decision.py`: `POLICY_VERSION`を`dogdb-v4:normalize=trim+collapse-whitespace+lowercase-outside-literals+strip-comments`へ更新する
- [ ] 5.2 `conn.dolly.stats()`のスナップショットへ、分類器実装（sqlglot）のバージョンを診断用メタフィールドとして追加する
- [ ] 5.3 テスト: `stats()`のsqlglotバージョンフィールドがdecision keyへ影響しないこと、イベントschemaに現れないことを検証する

## 6. golden fixture再生成とconformance確認

- [ ] 6.1 値非依存の性質テスト群（`test_determinism.py`、`test_faults.py`、`test_conformance.py`、`test_sql_scope.py`等）が全通過することを確認する
- [ ] 6.2 policy v4 golden fixtureをv4実装の出力から1回だけ再生成する（前例`policy_v3_golden.json`に倣った命名を実装時に確定する）
- [ ] 6.3 `tests/test_policy_regression.py`をv4基準線を参照するよう付け替える
- [ ] 6.4 バックエンド横断conformance（同一seed・同一SQL列に対するdecision一致）を`test_conformance.py`で再確認する
- [ ] 6.5 全テストを実行する（`.venv/bin/pytest`）

## 7. 判断記録の追記

- [ ] 7.1 `docs/decisions/rejected-alternatives.md`へ「計測先行のparser導入ゲート（D12、`expand-dolly-faults` design由来）」廃止を追記する（理由: 計測対象corpusが構造的に不在で無期限先送りと同義。事後検証（`unknown_sql`統計、W6-3）へ置換）
- [ ] 7.2 `docs/decisions/rejected-alternatives.md`へ「C1: Python下限（`>=3.12`）引き下げの検討」棄却を追記する（理由: 設計実験フェーズでは動機が薄く、検証コスト（sqlite3の3.12+挙動前提の回帰確認、CIマトリクス不在）に見合わない）

## 8. 文書更新と検証

- [ ] 8.1 `README.md`を更新する（sqlglot依存の追加、CTE/UNION分類拡張の説明、分類器のdialect中立性）
- [ ] 8.2 `openspec validate policy-v4-fingerprint-and-classifier`（または`openspec validate --change policy-v4-fingerprint-and-classifier`）が通ることを確認する

## 9. GitHub連携

- [ ] 9.1 issue #20へ完了コメントを投稿しクローズする（PRマージ後）
- [ ] 9.2 統括issue #19のスコープ表（#20行）とクローズ条件チェックリストを更新する（PRマージ後。C1棄却・D12ゲート廃止の記録完了項目を含む）
