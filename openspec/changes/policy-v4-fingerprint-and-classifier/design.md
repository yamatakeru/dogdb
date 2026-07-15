## Context

現行実装は2箇所とも「パーサ依存なし」を明示的な設計方針としている。`src/dogdb/core/sql.py`のモジュールdocstringは「Conservative SQL classification without a parser dependency.」と宣言し、深さ追跡付きの自前トークナイザで文型・FROMテーブル名・トップレベルLIMIT/OFFSETを抽出する。`src/dogdb/core/fingerprints.py:33-36`の`normalize_sql`は`trim → 空白畳み → lowercase`をSQL文字列全体へ一様に適用し、リテラル・コメント・識別子を区別しない。

この2つの実装上の判断が、外部レビューで指摘された2つの欠陥の直接の原因である。

1. **fingerprint正規化がリテラルを区別しない**: `SELECT 'DOG'`と`SELECT 'dog'`は正規化後に同一文字列になり、同一template fingerprintに畳み込まれる。同一templateのoccurrence系列が結合してしまうため、リテラル値だけが異なる別のテストケースが同じ決定系列を共有してしまう。
2. **分類器がCTE・複文等を無条件でUNKNOWNにする**: `classify_sql`は`top_level[0] == "select"`のときだけSELECT分類する。CTE（`WITH ... SELECT`）は`top_level[0] == "with"`のためUNKNOWNとなり、STASH/SHUFFLE等の対象から外れて無条件に素通しされる。利用者が「このクエリに障害を仕込んだつもり」でも実際には一度も注入されない、という発見しにくい罠になる。

隔離ブランチ`feature/improve-packaging-and-classifier`（`509f89c`、無認可実装のインシデント隔離ブランチ、経緯: yamatakeru/skills#10）はsqlglot分類器のedge case対処（UNION構造・LIMIT式除外・PRAGMA）を先行して試み、テスト通過実績もあるが、正規化がコメント非認識であるため本仕様と不一致であり、参照素材（叩き台）としてのみ扱う。コードは流用しない。

両欠陥への対応はいずれも`POLICY_VERSION`更新を要する。二段階の互換性断絶（先に正規化だけ更新、後で分類器導入のためもう一度更新）を避けるため、統括issue #19のグリルQ1決定により同一wave・同一POLICY_VERSION更新（v4）へ束ねる。

## Goals / Non-Goals

**Goals:**

- リテラル内容を保持しつつ、コメントは認識して除去する新しい正規化規則（v4）を定義し、`POLICY_VERSION`を1回だけ更新する。
- sqlglotによる文型分類へ直行し、CTE・UNION/EXCEPT/INTERSECTをSELECT扱いへ拡張する。計測先行ゲート（D12）は廃止する。
- 既存のスコープ抽出（`_from_tables`相当）とPAGE_HOLE用リテラル検出（`top_level_limit`/`top_level_offset`）を、同一意味論を保ったままsqlglot ASTベースへ再実装する。
- 分類器のバックエンド間dialect中立性を保証し、conformance契約（バックエンド横断のdecision一致）を壊さない。
- 分類器実装のバージョンを決定性の保証単位に組み込み、golden fixtureの再現条件を明確化する。

**Non-Goals:**

- イベントschema（v2）のフィールド集合・v1/v2混在ログ読み取りの変更。
- 素通し理由の正規語彙5種・`on_passthrough`厳格モード（W6-3）。
- `fault_probabilities`削除・確率語彙の正規化（W6-4）。
- `max_result_rows`によるbounded materialization（W6-5）。
- `INSERT/UPDATE…RETURNING`行への`on_result`介入の実装（将来候補として文書明記のみ）。
- Python下限（`>=3.12`）の引き下げ（C1、棄却）。

## Decisions

### D1: POLICY_VERSIONは `dogdb-v4:normalize=trim+collapse-whitespace+lowercase-outside-literals+strip-comments` とする

issue #20のグリルQ2・Q4で確定済みの文字列をそのまま採用する。サフィックスは正規化規則のみの意味的スコープとし、分類器（sqlglot導入・CTE/UNION拡張等）の規定は`POLICY_VERSION`文字列へ含めない。分類器の規定は契約本文（`docs/contract-v2.md`）に置く。これは「決定性の保証単位」と「POLICY_VERSION文字列が表す意味的スコープ」を分離し、分類器実装の詳細変更（例: sqlglotのパッチバージョン更新）のたびに`POLICY_VERSION`を更新する過剰結合を避けるための判断（issue #20 C節）。

**代替案（棄却）**: `POLICY_VERSION`に分類器のバージョンや規則summaryも含める案。分類器のマイナーな挙動修正のたびに文字列全体を更新する必要が生じ、正規化規則という決定キー入力の直接構成要素と、分類境界という間接的な挙動決定要因が同一の識別子に混在してしまうため見送り。

### D2: fingerprint正規化はリテラル保持スキャナ＋コメント除去を1パスで行う

正規化手順:

1. 単一引用符文字列リテラル（`''`エスケープ対応）を認識し、その内容（クォート文字自体は除く）は変更しない。
2. `--`行コメントと`/* */`ブロックコメントを認識し除去する。
3. リテラル外・コメント外の領域にのみ、先頭末尾のUnicode whitespace除去・連続whitespaceの単一ASCII空白化・lowercase変換を適用する。
4. 引用識別子（`"Foo"`）はlowercase維持（両バックエンドとも識別子は大小文字非区別のため、同一視が正しい）。
5. 方言的クォーティング（`$$…$$`等）は認識せず、対象外と契約に明記する（認識するのは単一引用符と`--`・`/* */`のみ）。

コメント認識はオプションではなく必須である。リテラル保持スキャナがコメントを認識しない場合、コメント内のアポストロフィ（例: `-- don't`）をリテラル開始と誤認し、以降の文字列走査全体が破綻する。これは隔離ブランチ`509f89c`の実装で確認済みの欠陥であり、「コメント非認識のリテラル保持実装」は構造的に成立しない（issue #20 A節）。

**代替案（棄却）**: コメントは保持しリテラルのみ保持する案。ORMが付与するコメントヒント（リクエストID等の実行ごとに変わる値）がfingerprintへ混入し、同一SQLテンプレートの実行がテンプレートごとに異なるfingerprintへ発散する。occurrence系列が育たないため、occurrenceに依存する状態系fault（OLD_BONE等）が実質的に無効化される。これがコメント除去を採用する直接の動機であり、v1契約「コメントは書き換えない」からの意図的逸脱である（ADR節に記録）。

### D3: 計測先行ゲート（D12）を廃止しsqlglotへ直行する

`expand-dolly-faults`のD12は「実アプリcorpusでUNKNOWN率（特にCTE）が支配的と計測されたときに初めてsqlglot導入を別changeで起票する」という計測先行ゲートだった。しかし計測対象となる実アプリcorpusはDogDBがテスト専用ツールという性質上構造的に存在せず、このゲートは実質的な無期限先送りとして機能してしまっていた。グリルQ1・Q3により、ゲートを廃止しsqlglot直行へ切り替え、導入効果の検証は事後測定（sqlglot導入後も残るUNKNOWN率を`dolly.stats()`から観測する、W6-3の`unknown_sql`統計）へ置き換える。

**代替案（棄却）**: D12ゲートの維持（測定機構を先に作り、閾値到達を待つ）。閾値をどう置いても「テスト専用ツールに実アプリcorpusを集める」という前提が成立しないため、事実上sqlglot導入が永久に起票されない。この点は`docs/decisions/rejected-alternatives.md`へ棄却理由として明記する。

### D4: 文型別の分類境界

| 文型 | v3（現行） | v4 |
|---|---|---|
| CTE（`WITH…SELECT`） | UNKNOWN素通し | **SELECT扱い** |
| UNION/EXCEPT/INTERSECT | UNKNOWN素通し | **SELECT扱い**（ORDER BYなし集合演算はSHUFFLE対象として正当） |
| `INSERT/UPDATE…RETURNING` | OTHER | OTHER維持。RETURNING行への`on_result`介入は将来候補として文書明記のみ |
| 複文（`;`区切り） | UNKNOWN素通し | 維持（介入対象文の意味論が曖昧、実行表面のバックエンド差が大きいため） |
| PRAGMA / EXPLAIN | UNKNOWN素通し | 維持 |
| parse失敗・分類不能ノード | UNKNOWN素通し | 維持（fallback堅持——sqlglotが未対応の構文やエラーを投げた場合も、例外を伝播させずUNKNOWNへ落とす） |

境界を動かすのは「SELECTの意味論を持つ文だけ」であり、素通し側の境界（複文・PRAGMA・parse失敗）は動かさない。これはissue #20 B節の確定方針をそのまま実装する。

**代替案（棄却）**: 複文の一部（先頭文のみ）を介入対象にする案。介入対象文がバックエンド実行表面のどの部分に対応するかが曖昧になり（DuckDB/SQLiteで複文の扱いが異なる）、決定性とconformanceの両方にリスクを持ち込むため見送り。issueの確定方針どおり複文は素通しのまま維持する。

### D5: 分類器のdialectは全バックエンド共通の方言中立parse（sqlglot generic dialect）に固定する

README記載のconformance契約は「同一seed・同一SQL列に対するdecisionのバックエンド横断一致」を保証する。分類器がバックエンドごとに異なるdialectでparseすると、同一SQL文字列がDuckDB側とSQLite側で異なる分類結果（例: 一方はSELECT、他方はUNKNOWN）を生みうる。これはconformance契約を直接破壊するため、dialectはバックエンドに関わらず単一の中立設定に固定する。

**代替案（棄却）**: バックエンドごとのネイティブdialect（`sqlglot.dialects.duckdb`/`sqlite`相当）を使う案。各バックエンドの構文拡張をより正確に解釈できる利点はあるが、conformance契約の「介入コアの一致」保証が壊れるため棄却（issue #20 C節）。

### D6: sqlglotのバージョンは範囲制約＋golden固定＋決定性保証単位への組み込み＋stats()メタフィールドの4点セットで管理する

- `pyproject.toml`はsqlglotを範囲制約（`>=採用版,<次メジャー`）で宣言する。
- golden fixtureは`uv.lock`が固定する特定バージョンのsqlglotの出力から生成する。
- `docs/contract-v2.md`の決定性保証単位（「同一seed、明示した同一session ID、同一設定、およびセッション先頭からの同一の順序付き入力列」）に「分類器実装（sqlglot）のバージョン一致」を追加する。sqlglotのマイナー・パッチバージョン差でAST構造や境界ケースの解釈が変わりうるため、異なるsqlglotバージョン間でのdecision列再現は保証しない。
- 診断目的で`conn.dolly.stats()`のスナップショットへsqlglotバージョンをメタ1フィールドとして追加する。これはdecision keyの入力にはならず、イベントschemaにも影響しない（利用者が「このgolden／replayログはどのsqlglotバージョンで記録されたか」を事後に確認するための帯域である）。

**代替案（棄却）**: sqlglotをdecision keyの直接入力（例: `derive`のタグにバージョン文字列を混入）にする案。決定性契約のタグ表（contract-v2.md）は用途ごとに閉じたタグ集合であり、実装バージョンという「システム構成」をdecision key自体に混ぜると、同一入力列でも依存関係更新のたびに全decision keyが変わってしまい、保証単位の説明責任がPOLICY_VERSION更新規約と重複する。保証単位の宣言（「バージョン一致が前提」という契約文）とstats()の診断メタフィールドの組み合わせで十分と判断した。

### D7: `_from_tables`相当・`top_level_limit`/`top_level_offset`はsqlglot ASTから同一意味論で再実装する

既存の挙動（トップレベルの`FROM`/`JOIN`テーブル名の保守的抽出、トップレベル`LIMIT`/`OFFSET`のリテラルのみ受理——`limit 5+5`のような式は不受理）はfault-injection specとcontract-v2に規範として既に存在し、v4はこれらの規範自体を変更しない。変更するのは実装手段（手書きトークナイザ→sqlglot AST走査）のみである。既存のfault-injection spec（PAGE_HOLE要件、スコープ要件）の文言・Scenarioはそのまま維持できる。

CTE・UNIONがSELECT分類の対象へ拡張されたことで、これらの文型に対して`_from_tables`相当のテーブル名抽出が新たに試みられることになるが、CTE本体内部・UNIONの複数分岐にまたがる場合の抽出結果の具体的な仕様（例: CTEエイリアス名を返すか、抽出不能として`None`を返すか）はissueに明記がない。この点はOpen Questionsに記載する。

## Risks / Trade-offs

- [golden fixture再生成が実装バグを固定化する] 再生成は「現実装の出力＝正」とするため、v4分類器・正規化の実装ミスもgoldenに焼き込まれうる → 再生成の前提条件として、(1) 分類・fingerprint関連の性質テスト群が全通過していること、(2) 受け入れ基準に列挙されたCTE/UNION/複文/PRAGMA/parse失敗の境界テストが全て通過していることを課す。
- [sqlglotの新規依存追加によるインストールサイズ・起動時間の増加] これまで分類器は「パーサ依存なし」（`sql.py`モジュールdocstライン1参照）を明示的な方針としていたが、本changeでこの方針を転換する。トレードオフとして、依存ゼロの単純さを失う代わりに、CTE・複文等の構造的な誤分類（罠）を解消する。ADR節に記録する。
- [sqlglotのバージョン差による分類結果の非決定性リスク] D6の4点セット（範囲制約・golden固定・保証単位明記・stats()メタフィールド）で緩和するが、範囲制約の上限（次メジャー未満）の間でも境界ケースの解釈が変わる可能性はゼロではない → CI環境ではuv.lock固定版のみを使用し、範囲制約は「動く組み合わせの許容幅」であって「decision再現性の保証範囲」ではないことを契約文書で明確に区別する。
- [CTE/UNIONへの介入拡大による既存利用者の想定外の挙動] v3では素通しされていたCTE/UNIONクエリが、v4では突然STASH/SHUFFLE等の対象になりうる。これは`POLICY_VERSION`更新済みの新バージョンとしての挙動であり、破壊的変更として明示する（BREAKINGラベル・ADR節）。

## Migration Plan

1. `docs/contract-v2.md`・`docs/contract-v1.md`を先に改訂し、v4正規化規則・決定性保証単位・RETURNING非規範注記を確定させる（実装の仕様源にする）。
2. `pyproject.toml`へsqlglot依存を追加する。
3. `src/dogdb/core/fingerprints.py`の`normalize_sql`をD2の手順へ書き換える。
4. `src/dogdb/core/sql.py`の`classify_sql`をsqlglotベースへ全面置換し、D4の境界表・D7の`_from_tables`相当・`top_level_limit`/`top_level_offset`相当を再実装する。dialectはD5のとおり全バックエンド共通の中立設定に固定する。
5. `src/dogdb/core/decision.py`の`POLICY_VERSION`をD1の文字列へ更新する。
6. `conn.dolly.stats()`にsqlglotバージョンのメタフィールドを追加する。
7. 受け入れ基準に列挙された境界テスト（リテラル大小・空白保持・エスケープ・コメント除去・CTE/UNION介入・複文/PRAGMA/parse失敗の素通し維持）を実装・全通過を確認する。
8. golden fixtureをv4実装の出力から1回だけ再生成し、バックエンド横断conformanceを確認する。
9. README・`docs/decisions/rejected-alternatives.md`（D12廃止・C1棄却）を更新する。
10. 全テスト実行、issueへの完了コメント・統括issue更新。ロールバックは単一PRのrevertで完結する（データ移行なし）。

## ADR: v3決定値互換の廃止と分類器依存方針の転換

**何が壊れるか**: 全`decision_key`・`event_id`・`treasure_id`・導出値（発火判定・行位置・順列・遅延量・保持期間・stale参照先など）・mood遷移スケジュール・HMAC化parameter fingerprintが変わる。さらに、v3でUNKNOWN素通しだったCTE・UNION文が新たにSTASH/SHUFFLE等の対象になりうるため、同一SQL列に対する介入の有無そのものが変わりうる。v3以前のイベントログと同じ決定系列を新バージョンで再現することは不可能になる。イベントログの**読み取り**はワイヤスキーマ規則（event-log spec）に従い引き続き可能。

**なぜ設計的に妥当か**:

1. **正規化v3の前提失効**: v3正規化（リテラル内容を含めた一様lowercase・空白畳み）は「SQL構文正規化ではない」という設計意図（contract-v1.md）のもとで単純さを優先した判断だったが、その単純さが「意味的に異なるSQL（`'DOG'` vs `'dog'`）が同一テンプレートに畳み込まれる」という実害を生むことが外部レビューで判明した。単純さより意味的正確さを優先すべきという前提の転換である。
2. **分類器「パーサ依存なし」方針の前提失効**: `sql.py`が明示していた「パーサ依存なし」の方針は、依存ゼロの単純さと引き換えに、CTE・複文等の構造的な文型を原理的にカバーできないという限界を内包していた。この限界は当初「保守的に安全側へ倒す」設計として正当化されていたが、外部レビューにより「安全側」ではなく「利用者が気づかない罠」として機能していることが判明した。計測先行ゲート（D12）という「実害が計測されるまで様子見る」判断も、テスト専用ツールという性質上、計測対象corpusが存在しないため機能しないことが分かった。これらの前提が失効した以上、sqlglot直行が設計的に妥当である。
3. **v1コメント不変更契約からの逸脱の正当化**: v1契約「コメントは書き換えない」は、SQL構文正規化を避けるという一般原則の一部だった。しかしコメント内容がfingerprintに混入することで、ORMのコメントヒントのようにテスト実行ごとに変わる値がoccurrence系列を破壊し、状態系fault（OLD_BONE等）を実質無効化するという副作用が判明した。「コメントは書き換えない」という一般原則よりも、「occurrence系列の安定性」という決定性契約の中核的な不変条件（`docs/decisions/rejected-alternatives.md`記載の「不安定fallback fingerprint」「occurrence辞書のeviction」棄却と同根の原則）を優先する。

**移行方法**: 旧決定値列の再現が必要な場合は、当該バージョン（policy v3を含む最後のリリース以前）のdogdbで再生成する。リポジトリ内の唯一の依存物（golden fixture）は本change内でv4基準線へ再生成する。`docs/contract-v1.md`・`docs/contract-v2.md`は歴史的文書としての失効注記を追加し、削除しない。

## Open Questions

- **CTE/UNIONに対する`_from_tables`相当のテーブル名抽出の具体的な結果**: issueは「同一意味論で再実装」とのみ規定し、CTE本体内部（`WITH cte AS (SELECT ... FROM real_table) SELECT * FROM cte`のような入れ子）でどのテーブル名を抽出すべきか（外側の`cte`エイリアスのみか、内部の`real_table`まで辿るか、あるいは抽出不能として`None`を返すか）を明記していない。既存の`_from_tables`は深さ0（括弧の外）のトークンのみを見る非再帰的な実装であり、「同一意味論」を字義通り適用するなら外側のFROM句のみを見て`cte`エイリアスを返す（内部へは辿らない）実装が候補になる。→ **確定（統括レビュー、2026-07-15）**: CTEエイリアス名ではなく、CTE本体内部で参照される実テーブルを含む実テーブル集合（エイリアス名は除外）を抽出する。エイリアス名を返す案は、利用者がスコープに指定するのは実テーブル名であるため `only_tables`/`exclude_tables` を構造的に空振りさせ、同名の実テーブルへの誤マッチも起こしうるため棄却。入れ子等の境界の詳細は実装時にテストで固定する。
- **UNION/EXCEPT/INTERSECTに対する`_from_tables`相当・`top_level_limit`/`top_level_offset`相当の扱い**: 複数の`SELECT`分岐が並ぶ文で「トップレベルのFROM」「トップレベルのLIMIT/OFFSET」が一意に定まらない場合（例: `SELECT * FROM a UNION SELECT * FROM b LIMIT 10`）の抽出規則もissueに明記がない。contract-v2.mdの既存原則（「保守的に抽出できた」もののみ対象、抽出不能文は`only_tables`指定時は対象外・`exclude_tables`指定時は対象）を延長し、複数分岐にまたがり一意に定まらない場合は抽出不能（`None`）として扱う案が保守的分類の原則に沿う。→ **方針確定（統括レビュー、2026-07-15）**: この保守的`None`案を採用し、具体的な境界は実装時にテストで固定する。
- **golden fixtureとテストファイルの命名**: `policy-v3-derivation-cleanup`の前例（`tests/fixtures/policy_v3_golden.json`、`tests/test_policy_regression.py`）に倣い`policy_v4_golden.json`等へ改名する想定だが、正式名称はtasks実装時に確定する。
