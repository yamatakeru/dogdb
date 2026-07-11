# Tasks: add-dogdb-mvp

## 1. ブートストラップ

- [x] 1.1 `git init` し、`.gitignore` を作成する（`.fusion-runs/`、`.venv/`、`__pycache__/`、`dist/`、`*.egg-info/`、`.pytest_cache/` を含む）
- [x] 1.2 uvプロジェクトを初期化する（`pyproject.toml`: パッケージ名 `dogdb`、`requires-python = ">=3.12"`、MIT、依存 `duckdb`、開発依存 `pytest`）
- [x] 1.3 MIT `LICENSE` を追加する
- [x] 1.4 パッケージ骨格を作る（`src/dogdb/` 配下に core / adapters / proxy のモジュール境界。design.md D1参照）
- [x] 1.5 初回コミットを作成する（OpenSpec artifacts含む）

## 2. Core基盤（バックエンド非依存）

- [x] 2.1 `LogicalResult`（columns / rows / rowcount）を実装する
- [x] 2.2 SQLテンプレート正規化と `template_fingerprint`（SHA-256）、HMAC化 `parameter_fingerprint` を実装する
- [x] 2.3 決定エンジンを実装する: `decision_key = SHA256(policy_version, seed, session_id, template_fingerprint, occurrence, phase)`、occurrence管理、`include_params` opt-in（design.md D2）
- [x] 2.4 エラー型階層を実装する（`DogDBError` 基底＋ `event_id`/`fault`/`phase`/`retryable`/`outcome` 属性、`DollyStashedError`、`DollyIgnoredError`。楽しい文言は `str()` のみ）
- [x] 2.5 JSONLイベントログのwriter/readerを実装する（schema v1必須フィールド、セッション内単調 `seq`、機密情報の既定非記録、破損行スキップ、出力先設定）
- [x] 2.6 house台帳を実装する（メモリ内宝物ストア、粘着状態、イベントログからの射影再構築関数）

## 3. 障害実装

- [x] 3.1 STASH行欠落モードを実装する（決定キー由来の行選択、house登録、`fault_injected` イベント）
- [x] 3.2 STASHエラーモードを実装する（`DollyStashedError` 送出、`Dolly took row #N to her house.` メッセージ）
- [x] 3.3 粘着STASHと返却を実装する（`return_all()` / `return_treasure(id)`、`treasure_returned` イベント、返却後の復帰）
- [x] 3.4 SHUFFLEを実装する（決定キー由来の順列。トップレベルORDER BYなしSELECTのみ）
- [x] 3.5 IGNOREを実装する（実行前送出、`outcome="not_executed"`、`retryable=True`、バックエンド無変化）
- [x] 3.6 1操作1 fault規則と優先順位（failure injection > silent mutation）、障害別確率設定を実装する

## 4. アダプタとプロキシ

- [x] 4.1 保守的SQL分類器を実装する（SELECT / ORDER BY有無 / 分類不能の3値。分類不能は無介入。design.md D7）
- [x] 4.2 DuckDBアダプタを実装する（`execute` / `close` / `in_transaction`、`description` の正規化）
- [x] 4.3 SQLiteアダプタを実装する（標準ライブラリのみ、DuckDBと同一の `LogicalResult` 構造）
- [x] 4.4 DB-APIプロキシを実装する（`wrap(conn, seed=...)` 必須seed、`connect()` 便宜関数、`execute`/`fetchall`/`fetchone`/`fetchmany`、論理結果セットへの一回介入、`executemany`・名前付きパラメータ・分類不能文の素通し、トランザクション委譲）
- [x] 4.5 `conn.dolly` 名前空間を実装する（`house()` / `return_all()` / `return_treasure(id)` / `log()`）

## 5. テスト（specsのScenarioを網羅）

- [x] 5.1 決定性テスト: 同一seed・同一クエリ列の2回実行でイベントログが一致（ts除外）。異seedで `decision_key` が異なる。UUIDパラメータでも既定設定で再現する。確認: `uv run pytest tests/test_determinism.py`
- [x] 5.2 house再構築テスト: STASH＋部分返却のログから射影を再建し、生のhouseと一致。確認: `uv run pytest tests/test_house.py`
- [x] 5.3 障害別テスト: STASH2モード、粘着と返却、SHUFFLE（ORDER BY尊重含む）、IGNORE（テーブル無変化＋リトライ成功）、1操作1fault優先規則、確率0で無風（素の接続と結果一致）。確認: `uv run pytest tests/test_faults.py`
- [x] 5.4 共通適合スイート: 同一シナリオをDuckDB/SQLite両アダプタで実行し、イベント列（fault / decision_key / outcome）が一致。coreが `duckdb`/`sqlite3` をimportしていないことの静的検査。確認: `uv run pytest tests/test_conformance.py`
- [x] 5.5 イベントログ契約テスト: schema v1必須フィールド、機密パラメータの平文非出現、単調seq、破損行スキップ。確認: `uv run pytest tests/test_event_log.py`
- [x] 5.6 全テスト通過を確認する。確認: `uv run pytest`

## 6. ドキュメントと仕上げ

- [x] 6.1 言語中立仕様書 `docs/contract-v1.md` を書く（イベントスキーマv1、決定関数、house意味論、fingerprint正規化規則。将来の他言語実装・プロキシ形態の契約）
- [x] 6.2 READMEを書く（ドリーの写真、クイックスタート、障害→実在障害クラス対応表、限界の明記: 行同一性は結果位置・単一writer・テスト専用ツール、キャッチコピー "Sometimes your data has gone to the doghouse."）
- [x] 6.3 実挙動確認: REPLでSTASH/SHUFFLE/IGNOREを発火させ、`Dolly took row #7 to her house.` が実際に出ること、`conn.dolly.house()` で宝物が見えることを目視確認する
- [x] 6.4 CodeRabbitによるcode-reviewを実施し、指摘に対応する（AGENTS.md要件）
- [x] 6.5 simplifyレビューを実施し、適用可能な簡素化を反映する（AGENTS.md要件）
- [x] 6.6 実装知見（SQL分類器の実介入率、アダプタ差分、メモリ上限の妥当値）を記録し、第二起票 `expand-dolly-faults` への反映点を洗い出す
