## Why

外部レビュー指摘5: SQLiteだけを使いたい利用者でも`duckdb`パッケージが必須依存になっている。技術的必然性はない——`wrap()`のバックエンド検出（`connection.py:596-601`）はモジュール名文字列によるduck-typingであり、`import duckdb`は`connect(backend="duckdb")`分岐内の遅延import（`connection.py:721`）のみで、アダプタ本体（`src/dogdb/adapters/duckdb.py`）はduckdbをimportしない。必須依存にする理由がないまま、SQLiteのみで使う利用者にduckdbのインストールコストを強いている。

## What Changes

- duckdbを`[project.optional-dependencies] duckdb = ["duckdb"]`へ移し、本体`dependencies`からduckdbを外す（W6-1で追加されmainへマージ済みのsqlglotは通常依存として維持する）。
- **BREAKING**: `dogdb.connect()`の既定`backend`を`"duckdb"`から`"sqlite"`へ変更する。判断根拠: 未リリースにつき既存コード破壊の前提が不在であり、既定は素のインストール（extras無し）で常に動くべきという原則を優先する。design.mdにADR節を設ける。
- `connect(..., backend="duckdb")`実行時にduckdb未導入だった場合、元の`ImportError`をchainした明瞭な`ImportError`を送出し、メッセージに`pip install "dogdb[duckdb]"`を明記する。
- dev dependency groupへduckdbを明示追加する（`dev = ["pytest", "duckdb"]`）。既存テストは全て従来どおり実行する。
- duckdb未導入環境の挙動を`sys.modules`のmonkeypatchで再現する2種のテストを追加する: ①`import dogdb`とSQLite経路が問題なく通ること、②`backend="duckdb"`が案内付き`ImportError`になること。
- READMEのクイックスタート直前にインストール行（`pip install "dogdb[duckdb]"`）を追記し、既定バックエンドのsqlite化を接続表面の説明・`connect()`の案内文・docstringへ表記の全数更新として反映する。

### Non-goals

- sqlglotの追加、fingerprint正規化、POLICY_VERSION更新（W6-1でmainへマージ済み）。POLICY_VERSIONはこのchangeでは触らない。
- リポジトリにCIが存在しないため、duckdb抜き環境のCIマトリクスは作らない。将来CI導入時の検証項目としてのみdesign.mdに記す。
- `wrap()`（既存接続を包む経路）の既定バックエンド選択は対象外。`wrap()`は接続オブジェクトのモジュール名から検出するため既定値の概念がなく、変更しない。

## Capabilities

### New Capabilities

（なし。パッケージング（extras化）自体はインストール構成の変更でありspec-level要件ではないため、proposalのImpactとdesign/tasksで扱う。）

### Modified Capabilities

- `dbapi-proxy`: 「接続のラップ」要件に、便宜関数`dogdb.connect()`の既定`backend`が`"sqlite"`であること、および`backend="duckdb"`指定時にduckdb未導入なら案内付き`ImportError`を送出することを追加する。

## Impact

- **コード**: `pyproject.toml`（`dependencies`からduckdb除去・`[project.optional-dependencies]`追加・dev group更新）、`src/dogdb/proxy/connection.py`（`connect()`の`backend`既定値変更、duckdb未導入時のImportErrorメッセージ整備）。`_adapter_for`・アダプタ本体・`wrap()`は変更しない（duckdbをimportしないため対象外）。
- **テスト**: duckdb未導入相当を`sys.modules`monkeypatchで再現する新規テスト2種、およびImportError案内メッセージのテスト。既存テストは変更なしで全て通過する想定。
- **文書**: `README.md`（インストール行追加、既定バックエンド表記の全数更新）、`connect()`のdocstring（既定値を明記）。
- **利用者影響**: `dogdb.connect(path, seed=...)`を`backend`省略で呼んでいた既存コード（未リリースのため外部利用者はゼロ）は、既定の接続先がDuckDBからSQLiteへ変わる（**BREAKING**）。`wrap()`経由の利用や`backend`を明示指定していた呼び出しは影響を受けない。
- **依存関係**: W6-1（sqlglot追加）はmainへマージ済みのため、`dependencies`節のchange間コンフリクトの前提は解消済み。duckdb除去後の`dependencies`は`sqlglot`のみとなる。
