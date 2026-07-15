## Context

`duckdb`は現在`pyproject.toml`の必須`dependencies`にあるが、技術的必然性はない。`wrap()`のバックエンド検出（`connection.py:596-601`、`_adapter_for`）はモジュール名文字列によるduck-typingであり、`import duckdb`は`connect(backend="duckdb")`分岐内（`connection.py:721`）の遅延importのみ。`src/dogdb/adapters/duckdb.py`（`DuckDBAdapter`）自体は`duckdb`パッケージをimportしない——生接続オブジェクトを不透明な値として扱うのみ。したがって`import dogdb`自体、および`wrap()`へduckdb接続を渡す経路は、duckdb未導入でも成立する（渡された時点で呼び出し側がduckdbを導入済みだから）。影響が生じるのは`connect(backend="duckdb", ...)`という便宜関数の遅延import一箇所だけである。

グリルセッション（issue #21）で仕様は決定済み。本design.mdは実装方針の確定と、issueが明示していない細部の最小スコープ解決を記録する。

## Goals / Non-Goals

**Goals:**

- `duckdb`を`[project.optional-dependencies]`へ移し、本体`dependencies`から除去する。
- `dogdb.connect()`の既定`backend`を`"sqlite"`へ変更し、素のインストール（extras無し）で`import dogdb`と最小のSQLite経路が常に動くようにする。
- `backend="duckdb"`指定時にduckdb未導入なら、原因（元の`ImportError`）をchainした案内付き`ImportError`を送出する。
- 既定バックエンドのsqlite化を、README・`connect()`のdocstring・examplesの既定表記へ反映する。

**Non-Goals:**

- `wrap()`の挙動変更。`wrap()`は渡された接続オブジェクトのモジュール名から検出するため「既定バックエンド」という概念を持たず、対象外。
- sqlglot追加・fingerprint正規化・POLICY_VERSION更新（W6-1でmainへマージ済み）。POLICY_VERSIONは本changeでは変更しない。
- duckdb抜き環境のCIマトリクス新設。リポジトリにCIは存在しないため作らない。将来CI導入時の検証項目としてのみ本文書に記す。
- `_adapter_for`・`src/dogdb/adapters/__init__.py`・`DuckDBAdapter`本体の変更。いずれも`duckdb`をimportしないため、遅延import化の対象にならない（D3参照）。

## Decisions

### D1: 本体`dependencies`からduckdbのみを除去し、duckdbは`optional-dependencies`へ

`dependencies = ["sqlglot>=30.12.0,<31"]`（W6-1で追加されたsqlglotを維持しduckdbのみ除去）、`[project.optional-dependencies] duckdb = ["duckdb"]`、`[dependency-groups] dev = ["pytest", "duckdb"]`とする。duckdbのバージョン指定は現状の`dependencies`エントリが無指定だったことに合わせ、追加しない。

sqlglotの追加はW6-1で実施されmainへマージ済みであり、本changeは`dependencies`からduckdbのみを除去する。除去後の`dependencies`にsqlglotが残ることが本changeの完了形である。

### D2: `connect()`の既定値のみ変更し、`wrap()`は変更しない

「既定バックエンド」はキーワード引数`backend`のデフォルト値としてのみ存在し、それを持つ公開APIは`connect()`だけである。`wrap()`は接続オブジェクトの型から検出するため、対象外。

### D3: `_adapter_for`／アダプタ本体は変更しない（隔離ブランチとの差分）

参照素材である隔離ブランチ`509f89c`（親コミット`d337a4c`）は`_adapter_for`内の`DuckDBAdapter`importを`_lazy_duckdb_adapter()`ヘルパーで遅延化していたが、これは不要と判断する。`_adapter_for`が呼ばれるのは`wrap()`に生接続オブジェクトが渡された時点であり、その接続オブジェクトが存在する時点で呼び出し側は既にduckdbパッケージを導入済みである。`DuckDBAdapter`モジュール自体も`import duckdb`を持たない。したがって`from dogdb.adapters.duckdb import DuckDBAdapter`をモジュールトップレベルに置いたままでも、duckdb未導入環境での`import dogdb`は成立する。隔離ブランチの遅延化は過剰対応であり、採用しない。

### D4: duckdb未導入時のImportErrorは`connect()`内の`import duckdb`を`try/except ImportError`で捕捉し、chainして再送出する

メッセージは最低限「`backend="duckdb"`にはduckdbパッケージが必要」と`pip install "dogdb[duckdb]"`というインストール手順を含む。`raise ImportError(...) from exc`で元の`ImportError`をchainし、根本原因（未インストールかimportエラーか）をトレースバックから追跡可能にする。既存の`backend`不正値に対する`ValueError`分岐とは独立した経路であり、衝突しない。

### D5: `connect()`に既定値を明記する最小のdocstringを追加する

現状`connect()`にdocstringは存在しない。受け入れ基準は「docstring・README・examplesの既定表記の全数更新」を求めるが、リポジトリを走査した結果、既定バックエンドを記述する既存のdocstring・example内表記は存在しなかった（examplesは全て`dogdb.wrap()`を使い`connect()`を呼ばない）。既定値がコードのデフォルト引数にしか存在しない状態は、変更後の既定値をユーザーが発見しにくくする。受け入れ基準の意図（利用者が既定バックエンドを正しく認識できること）を満たすため、`backend`の既定値が`"sqlite"`である旨を1文で記す最小docstringを新設する（Open Questions参照）。

### D6: README更新は3箇所に限定する

issue #21の指示（「クイックスタート直前にインストール行を追記し、既定バックエンドのsqlite化を接続表面の説明・`connect()`の案内文に反映する」）に対応する箇所を特定した:

1. クイックスタート（`import duckdb`を使う例）の直前に`pip install "dogdb[duckdb]"`の行を追記する。
2. 「バックエンド別の接続表面」節の導入文へ、`connect()`の既定バックエンドがSQLiteである旨を追記する。
3. クイックスタート直後の`connect()`案内文（`dogdb.connect("test.sqlite", backend="sqlite", seed=42)` / `backend="duckdb"`の説明行）を、既定値の言及を含む形へ更新する。

`docs/contract-v1.md` / `docs/contract-v2.md`は対象外とする（Open Questions参照）。

## Risks / Trade-offs

- [pyprojectの依存節がW6-1（sqlglot追加）とコンフリクトする] → W6-1が先行してmainへマージされたため解消済み。本changeはマージ後のmainを基点に`dependencies`からduckdbのみを除去し、単独でも`openspec validate`・テストが通る状態を保つ。
- [`connect()`の既定変更に気づかない呼び出し側が、意図せずSQLiteへ接続する] → 未リリースのため外部利用者はゼロで実害は生じない。ADR節・README・docstringで明示し、破壊的変更ポリシー（タグ前は通常の選択肢）に従う。
- [duckdb未導入環境の検証がCIで自動化されない] → `sys.modules`monkeypatchによるテストをリポジトリに常置し、ローカル・将来CI導入時のいずれでも実行可能にする。

## Migration Plan

1. `pyproject.toml`: `dependencies`からduckdbを除去する（W6-1で追加されたsqlglotは維持する）、`[project.optional-dependencies] duckdb = ["duckdb"]`を追加する、`dev` groupへduckdbを追加する。
2. `src/dogdb/proxy/connection.py`: `connect()`の`backend`既定値を`"sqlite"`へ変更し、`import duckdb`を`try/except ImportError`で囲んでchain付き案内`ImportError`を送出する。`connect()`へ既定値を明記するdocstringを追加する。
3. `README.md`: D6の3箇所を更新する。
4. テスト: `sys.modules`monkeypatchによる2種のテスト（duckdb不在での`import dogdb`＋SQLite経路、`backend="duckdb"`の案内付き`ImportError`）と、ImportErrorメッセージに`pip install "dogdb[duckdb]"`が含まれることを検証するテストを追加する。
5. 既存テストを全て実行し従来どおり通過することを確認する。`openspec validate`を通す。
6. wave集約時: 統合後に全テストと全changeの`openspec validate`を再実行する（W6-1はmainへマージ済みのため、`pyproject.toml`のchange間差分統合は不要）。

ロールバックは単一PRのrevertで完結する（データ移行なし、影響ファイルは`pyproject.toml`・`connection.py`・`README.md`・テストのみ）。

## ADR: `connect()`既定バックエンドをDuckDBからSQLiteへ変更する

**何が壊れるか**: `dogdb.connect(path, seed=...)`を`backend`省略で呼んでいた既存コードは、接続先がDuckDBからSQLiteへ変わる。SQLite表面とDuckDB表面は`dbapi-proxy` specが定義するとおり公開APIが異なる（`execute()`の返り値、`fetchall`等の接続レベル有無、`with`文の意味論）ため、`backend`省略の呼び出し側は表面の違いによる実行時エラーに遭遇しうる。

**なぜ設計的に妥当か**: 本プロジェクトは最初のタグ付きリリース前であり、既存コード破壊を懸念すべき外部利用者が存在しない。この前提の不在こそが、通常であれば据え置くはずの既定値変更を「破壊的だが妥当な選択肢」に変える。加えて、`duckdb`をoptional-dependencyへ移す本changeの主目的（SQLite専用利用者のインストールコスト削減）に対し、`connect()`の既定値が`"duckdb"`のままでは矛盾する——素のインストール（`pip install dogdb`のみ）で`connect()`を省略引数のまま呼ぶと`ImportError`になり、「追加インストール無しで常に動く」という既定の原則が破られる。既定は常に、追加インストールなしで動く経路を指すべきである。

**移行方法**: `backend`を明示指定していた呼び出し（`backend="duckdb"`または`backend="sqlite"`）は影響を受けない。省略していた呼び出しは、DuckDBが必要な場合`backend="duckdb"`を明示するか`pip install "dogdb[duckdb]"`を実行し、SQLiteで問題ない場合は変更不要。移行手順はREADMEとdocstringに記載する。

## Open Questions

以下はissue #21が明示していない点であり、最小スコープで解決した上でここに記録する（issueへの新規判断の書き足しではなく、issueの沈黙箇所の扱い）。

- **`docs/contract-v1.md`／`docs/contract-v2.md`は「表記の全数更新」の対象に含まれるか**: 対象外と判断した。両文書は実装言語・DBドライバに依存しない相互運用契約であり、インストール手順や`connect()`の既定値を記述する表記が現状存在しない（`grep`で確認済み）。更新すべき既存の表記が無いため、本changeでは触れない。将来これらの文書にインストール前提が追加された場合は別途検討する。
- **`connect()`への新規docstring追加は「更新」の範囲か「新設」であり得るか**: 追加する側に倒した（D5）。既存のdocstring・example内表記はゼロ件だったが、受け入れ基準の趣旨（既定バックエンドの変更を利用者が発見できること）を満たすには、コードのデフォルト引数以外に既定値を明文化する箇所が最低一つ必要と判断した。
