# Proposal: add-dogdb-mvp

## Why

データ層の堅牢性（リトライ、暗黙順序依存、欠落データへの耐性）をテストする道具は、インフラ層を壊すもの（Jepsen, Toxiproxy）ばかりで、**SQLの意味論レベルで決定的に再現可能な障害を注入するもの**が存在しない。DogDBは「犬（ドリー）がデータをハウスへ持ち去る」という物語で、可逆的なデータの不在・順序攪乱・タイムアウトを seed 決定的に注入するカオスDBラッパーを提供する。設計はブラインドパネル（fusion 3ワーカー）と grilling による擦り合わせで確定済みであり、小さく作って育てるため、読み取り系障害のみの最小構成を第一実装として出荷する。

## What Changes

- 新規Pythonパッケージ `dogdb`（Python 3.12+ / uv / MIT）を作成する。
- DB-APIプロキシ `dogdb.wrap(conn, seed=...)` / `dogdb.connect(...)` を追加する。ドリー操作は `conn.dolly` 名前空間に隔離する。
- 読み取り系障害4種を実装する: **STASH**（行をハウスへ隠す。行欠落 / `DollyStashedError` の2モード）、**SHUFFLE**（結果順序の攪乱）、**IGNORE**（実行前タイムアウト＝lost request）、**手動RETURN**（隠した宝物の返却）。
- **Dog House台帳**を実装する: STASHはセッション内で粘着し、返却まで同じクエリで隠れ続ける。houseはイベントログの射影として再構築可能。
- **JSONLイベントログ**（schema_version付き、機密情報を既定で記録しない）と、テストからassert可能なログアクセスAPIを追加する。
- **決定的障害選択**: `H(seed, セッション, SQLテンプレートfingerprint, 出現回数, phase)` による決定キー。同一seed＋同一入力列→同一イベント列を保証する。
- **バックエンドアダプタ**: DuckDBとSQLiteの2実装。障害エンジンは論理結果セットに対して一度だけ書き、アダプタは正規化のみを担う薄い糊とする。
- 構造化エラー型階層（`DogDBError`基底、機械可読属性、注入エラーと実DBエラーの型判別）を追加する。
- プロジェクトブートストラップ: git init、`.gitignore`（`.fusion-runs/` 含む）、uvプロジェクト、MIT LICENSE、ドリー写真つきREADME。

### Scope（このchangeに含むもの）

読み取り系障害のみ。`execute` / `fetchall` / `fetchone` / `fetchmany`、位置パラメータのみ対応。1操作につき最大1 fault。

### Non-goals（このchangeに含まないもの）

以下は**第二起票 `expand-dolly-faults` へ送る**（本changeの実装過程で得た知見により第二起票側が更新されることを許容する）:

- 追加障害: ECHO（重複行）、TAIL_CHASE（途中打ち切り）、FALSE_EMPTY、PAGE_HOLE、SLOTH（遅延）、BARK、GUARD_BOWL、CHEW（具体プロファイル限定）、TANGLED_LEASH、WRONG_COUNT、OLD_BONE（stale read）
- mood状態機械（相関障害）、RETURN_TREASURE自動返却、IGNOREのlost response分割
- 書き込み系障害の設計調査（orphan write等）

以下は**恒久的またはMVP圏外の非目標**:

- ZOOMIES（スキーマ破壊）: Result House方式では再現不能かつ危険。pgwire/Entity House以前は非目標
- 任意クエリ変異（頼んだのと違うSQLの黙示実行）: razor不通過のため不採用
- Entity House（行同一性追跡）、pgwireプロキシ、ORM（SQLAlchemy）統合、`executemany`への障害注入、名前付きパラメータ、複数プロセス同時ログ書き込み、透過エラーモード

## Capabilities

### New Capabilities

- `dbapi-proxy`: DB-APIプロキシの公開表面。`wrap`/`connect`、対応メソッド範囲、`conn.dolly`名前空間、トランザクション素通し、対応範囲外操作の扱い
- `fault-injection`: 障害モデル。4障害の意味論、silent mutation / failure injection の2分類、1操作1 fault規則、保守的SQL分類、エラー型階層
- `dog-house`: 宝物台帳。粘着STASH、返却操作、house＝イベントログ射影の不変条件
- `event-log`: JSONLイベントログ。スキーマv1、機密性既定、単一writer契約、テスト向けassert API
- `determinism`: 決定キー、fingerprint規則（パラメータ既定除外＋opt-in）、replay保証、wall-clock禁止
- `backend-adapters`: アダプタ契約と論理結果セット、DuckDB/SQLite実装、共通適合テストスイート

### Modified Capabilities

（なし — 新規プロジェクトのため既存specはない）

## Impact

- **コード**: 全て新規。既存コードへの影響なし。
- **依存**: 実行時 `duckdb`（SQLiteは標準ライブラリ）。開発時 `pytest`、`uv`。
- **外部公開**: PyPI名 `dogdb`（空き確認済み 2026-07-11）。公開自体は本changeの必須成果物ではない。
- **後続**: 第二起票 `expand-dolly-faults` は本changeのspecs（特に `fault-injection` と `determinism`）を基底として差分を積む。本changeの実装知見（アダプタ差・分類器の精度）が第二起票の内容を更新し得る。
- **開発フロー**: 実装はCodexへ委譲、CodeRabbitレビューを最低一度実施、simplifyを検討（AGENTS.md準拠）。
