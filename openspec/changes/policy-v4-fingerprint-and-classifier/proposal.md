## Why

外部レビュー指摘の妥当性判定（統括issue #19、Fusionパネル3ワーカー全員一致）により、次の2点が事実として確認された。指摘1: fingerprint正規化がリテラル内も小文字化・空白畳みするため、`SELECT 'DOG'` と `SELECT 'dog'` が同一template occurrence系列に結合してしまう。指摘2: 自前字句解析の分類器がCTE・複文等を無条件でUNKNOWN扱いし素通しするため、「注入したつもりが素通り」という利用者の罠になる。両者はいずれも`POLICY_VERSION`更新を要する変更であり、二段階の互換性断絶を避けるため同一waveで1回（v4）に束ねる（統括issue #19 グリルQ1決定）。

## What Changes

- **BREAKING**: `POLICY_VERSION` を `dogdb-v4:normalize=trim+collapse-whitespace+lowercase-outside-literals+strip-comments` に更新する。POLICY_VERSIONはdecision key・HMACキー・moodキーの導出入力であるため、全決定値・全イベント列・既存golden fixtureが失効する。
- fingerprint正規化をv4規則へ更新する: 単一引用符リテラルの内容は**保持**する（`''`エスケープ対応）。コメント（`--`・`/* */`）は**認識して除去**する。引用識別子（`"Foo"`）は引き続きlowercase維持（両バックエンドとも識別子は大小文字非区別のため）。方言的クォーティング（`$$…$$`等）は**対象外**と契約に明記する（認識するのは単一引用符と`--`・`/* */`のみ）。
- コメント除去はv1契約「コメントは書き換えない」からの意図的逸脱であり、design.mdにADRとして記録する（動機: ORMのコメントヒント（リクエストID等）が毎fingerprintを変え、occurrence系列が育たず状態系fault（OLD_BONE等）が無効化されるのを防ぐ）。
- SQL分類器をsqlglotへ置き換える。計測先行ゲート（`expand-dolly-faults` design D12）は廃止し、sqlglot直行とする（理由: 計測対象corpusが構造的に不在で、計測先行は事実上の無期限先送りと同義。導入効果の検証は事後測定（`unknown_sql`統計、W6-3）に置換）。
- 文型別の分類境界を変更する: CTE（`WITH…SELECT`）とUNION/EXCEPT/INTERSECT（ORDER BYなし集合演算はSHUFFLE対象として正当）を**SELECT扱い**に拡張する。`INSERT/UPDATE…RETURNING`はOTHER維持（RETURNING行への`on_result`介入は将来候補として文書に明記するのみで実装しない）。複文（`;`区切り）・PRAGMA/EXPLAIN・parse失敗や分類不能ノードはUNKNOWN素通しを維持する（fallback堅持）。
- 分類器のdialectは全バックエンド共通の方言中立parse（sqlglot generic dialect）に固定する。バックエンド別dialectは使わない（README記載のconformance契約——同一seed・同一SQL列に対するdecisionのバックエンド横断一致——を壊すため）。
- `_from_tables`相当（scopeの`only_tables`/`exclude_tables`が使うテーブル名抽出）と`top_level_limit`/`top_level_offset`（PAGE_HOLE用、リテラルのみ受理、`limit 5+5`のような式は不受理）を、既存と同一の意味論を保ったままsqlglot ASTから再実装する。
- sqlglotの依存バージョンをpyprojectで範囲制約（`>=採用版,<次メジャー`）し、golden fixtureはuv.lockの固定版から生成する。決定性の保証単位（contract-v2）に「分類器実装（sqlglot）のバージョン一致」を追加する。診断用に`conn.dolly.stats()`のスナップショットへsqlglotバージョンをメタ1フィールド追加する（イベントschemaは不変）。
- policy v4 golden fixtureを再生成し、バックエンド横断conformance（同一seed・同一SQL列に対するdecision一致）を維持することを確認する。
- `docs/contract-v2.md`を改訂（正規化規則・決定性保証単位・RETURNING非規範注記）し、`docs/contract-v1.md`にv4失効の追記を行う。READMEを更新する（依存追加・分類境界の説明）。
- `docs/decisions/rejected-alternatives.md`へ「計測先行のparser導入ゲート（D12）」廃止と、「C1: Python下限（`>=3.12`）引き下げの検討」棄却を追記する。

### Non-goals

- イベントschema（`schema_version: 2`、フィールド集合、v1/v2混在ログ読み取り）の変更はしない。
- 素通し理由の正規語彙5種・`on_passthrough`厳格モードの導入はW6-3（#22）の射程。既存の分類統計（分類済みSELECT数・UNKNOWN数・介入数）の粒度はそのまま使う。
- `fault_probabilities`削除・発火確率の用語正規化はW6-4（#23）の射程。
- `max_result_rows`によるbounded materializationはW6-5（#24）の射程。
- `INSERT/UPDATE…RETURNING`行への`on_result`介入の実装（本changeは将来候補としての文書明記のみ）。
- Python下限（`>=3.12`）の引き下げ（C1、棄却済み。理由をrejected-alternatives.mdへ記録する）。
- 隔離ブランチ`feature/improve-packaging-and-classifier`（`509f89c`）の採用。参照素材（叩き台・edge case発見源）としてのみ扱い、コードの流用はしない（正規化がコメント非認識のため本仕様と不一致）。

## Capabilities

### New Capabilities

- `sql-classification`: sqlglotベースの文型分類境界（CTE/UNIONのSELECT拡張、RETURNING/複文/PRAGMA/parse失敗の素通し維持）、分類器のdialect中立性、分類器実装のバージョン管理を定義する。

### Modified Capabilities

- `determinism`: SQLテンプレートfingerprintのv4正規化規則（リテラル保持・コメント除去）を新設し、決定性の保証単位に「分類器実装（sqlglot）のバージョン一致」を追加する。
- `fault-injection`: スコープ抽出が不能な文の例示を更新する（CTEはv4でSELECT分類対象となり抽出を試みうるため、例示を複文へ差し替える）。
- `dbapi-proxy`: `conn.dolly.stats()`の診断用メタフィールドにsqlglotバージョンを追加する。

## Impact

- **コード**: `src/dogdb/core/fingerprints.py`（`normalize_sql`のv4書き換え）、`src/dogdb/core/sql.py`（sqlglotベースの分類器へ全面置換）、`src/dogdb/core/decision.py`（`POLICY_VERSION`更新）、`pyproject.toml`（sqlglot依存追加）。
- **テスト**: policy v4 golden fixtureの再生成、既存の分類・fingerprint関連テストの全面更新、バックエンド横断conformanceスイートの再確認。
- **文書**: `docs/contract-v2.md`、`docs/contract-v1.md`、`README.md`、`docs/decisions/rejected-alternatives.md`。
- **利用者影響**: v3以前の決定値・イベント列に依存するreplayは再現不能になる（**BREAKING**）。外部利用者はゼロ、タグ付きリリース前のため破壊的変更ガバナンスの通常選択肢として実施する。ADR節をdesign.mdに必須で設ける。
- **依存関係**: 他waveとの直列依存はない。`pyproject.toml`の依存節はW6-2（#21、duckdb extras化）とも交差するため、wave集約時に親が統合する。W6-3（#22）の`unknown_sql`観測値の意味は本changeの前後で変わる（本change導入後の値が「sqlglotでも残る穴」になる）。
