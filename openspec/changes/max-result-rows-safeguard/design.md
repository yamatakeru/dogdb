## Context

`execute()`は現在、adapterが`cursor.fetchall()`で全行を一括materializeしてから`LogicalResult`を組み立てる（`src/dogdb/adapters/base.py:30-37`）。`max_intervention_rows`（既定10,000）はこのmaterialize済み結果に対する「fault適用の対象行数上限」であり、取得件数やメモリの上限ではない（`src/dogdb/core/faults.py:357-375`、`src/dogdb/proxy/connection.py:170-186`）。README・contract-v2.mdはこの限界を既に文書化しているが、真の意味でのメモリ保護手段が存在しない。

streaming介入は決定性を壊すため却下済み（`docs/decisions/rejected-alternatives.md`）、切り詰め返却もsilent corruptionとしてW1-cで却下済みである。両判断と矛盾しない唯一の方向は、opt-inで「上限を超えたら読み取りを打ち切り、部分結果を返さずエラーにする」安全弁であり、これが本changeの`max_result_rows`である。

グリルセッション（issue #24）で仕様は決定済み。本designは、決定済みの観測可能契約を満たすための実装アーキテクチャ（アダプタ⇔コア間のシグナル伝達方式、row_cap適用スコープ、イベント構築方法）を扱う。

## Goals / Non-Goals

**Goals:**
- `max_result_rows`超過時に、アダプタ層でバックエンド結果を全件読み切る前に読み取りを打ち切れるようにする（真のメモリ上限）。
- 打ち切りも決定的に再現し、occurrence・論理時計は他の操作と同様に前進させる。
- `limit_exceeded`イベント・`DollyLimitError`という既存語彙を再利用し、新しいイベント種別や例外型を増やさない。
- `max_intervention_rows`とは独立の直交ノブとして実装し、結合バリデーションを持たない。

**Non-Goals:**
- streaming介入の実現（却下判断は維持。本changeはその布石ではない）。
- 部分結果の切り詰め返却（W1-c却下の再導入はしない）。
- `max_intervention_rows`のデフォルト値・fault適用ロジックの変更。
- `POLICY_VERSION`の更新（決定導出には無関係）。
- UNKNOWN分類・名前付きパラメータ・トランザクション文などの素通し経路への`row_cap`適用（D2で理由を述べる）。
- stale-read-cacheとの専用の相互作用仕様化（中断した操作は`on_result`決定自体が発生しないため、キャッシュへは自然に記録されない。副作用として許容し、専用のRequirementは設けない）。

## Decisions

### D1: アダプタ→コア間のシグナル伝達は内部シグナル例外を新設する

アダプタが`row_cap+1`行目を観測して中断する際、`LogicalResult`を返さず、呼び出し側（`proxy/connection.py`）が識別可能な形で中断を伝える必要がある。

**採用**: `dogdb.adapters.base`に内部限定の軽量シグナル例外（例: `RowCapExceeded`）を新設し、アダプタはこれを送出する。`proxy/connection.py`の`execute()`はこの例外を捕捉し、`FaultEngine`側に新設する`limit_exceeded`イベント生成ヘルパーを呼び出してイベント記録後に`DollyLimitError`を送出する。この例外は`dogdb.__init__`のpublic exportに含めず、実装内部の制御フローに限定する。

**代替案と却下理由**:
- `LogicalResult`にsentinelフラグ（例: `truncated=True`）を持たせて返す方式 — 却下。「部分結果は返さない」という決定済み意味論と、`LogicalResult`が「完成した論理結果」を表す既存の型契約に反し、下流（stale cache・fault適用）が誤って部分結果を処理するリスクがある。
- アダプタが直接`DollyLimitError`を送出する方式 — 却下。`DollyLimitError`の必須属性（`event_id`・`retryable`・`outcome`等）は`decision_key`など decision engine 側の情報を要し、アダプタ層はdecision engine・event log・houseに依存しないレイヤ分離を保ちたい。

### D2: `row_cap`の適用スコープは`max_intervention_rows`検査と同一にする

issue本文は`row_cap`適用範囲（全操作か、分類・スコープ済み操作限定か）を明示していない。受け入れ基準の「before_execute faultとの順序（BARK先行）テスト」は、BARK等のbefore_execute fault評価が行われる経路（=分類器がSELECTと判定し、`only_tables`/`exclude_tables`スコープに含まれる操作）でのみ意味を持つ。この対応関係から、`row_cap`適用スコープを既存の`oversized_result`計算（`scoped_select = scoped and classification.kind is SQLKind.SELECT`）と同一に限定するのが最小スコープの補完と判断した。UNKNOWN分類・名前付きパラメータ・トランザクション文・fingerprint入力域外パラメータ等の素通し経路は本changeの対象外とする。

この判断はissueの沈黙点への補完であり、「未解決の疑問」にも記載する。

### D3: `limit_exceeded`イベントの構築は「decision_key導出」と「on_result決定の評価」を区別する

契約文書（`docs/contract-v2.md`「イベント schema v2」）は`limit_exceeded`の必須フィールドとして`phase`・`template_fingerprint`・`parameter_fingerprint`・`occurrence`・`decision_key`・`outcome`・`details`を定めている。本changeは既存event typeを再利用するため、この必須フィールド集合を満たさなければならない。一方でissueは「中断時はon_result決定を評価しない（`decision_evaluated`イベントは出ない）」とも定めている。

**採用**: `DecisionEngine.decide(phase="on_result", ...)`（seed・session・template・occurrence・phaseからのSHA-256導出のみで、確率的なfault選択を伴わない純粋関数）は呼び出し、その`Decision`を`limit_exceeded`イベントの`decision_key`等の構築にのみ用いる。`FaultEngine.on_result`（fault候補選択と、発火なし時に`decision_evaluated`を記録する`_debug_decision`フォールバック）は一切呼び出さない。これにより「`decision_evaluated`は出ない」という決定済み意味論と、「`limit_exceeded`は契約上の必須フィールドを満たす」という既存契約の両方を満たす。

この区別（decision keyの導出 ≠ on_resultのfault評価）はissue本文が明示的に述べたものではなく、既存契約の必須フィールド表から逆算した設計解釈である（統括レビュー2026-07-15で既存コードとの突合により確定——「未解決の疑問」参照）。

実装順序は次のとおりとする: ①`before_execute`評価（既存経路のまま。BARK等はここで先行発火し得る）→②`row_cap`付きアダプタ読み取り→③中断シグナル受領時、mood・自動返却の論理時計を通常経路と同一のフックで前進→④中断した操作のoccurrence消費とdecision導出は既存の`max_intervention_rows`超過経路と同一の規則に従い（二重消費なし）、そのDecisionから`limit_exceeded`を構築・記録→⑤`DollyLimitError`送出。`FaultEngine.on_result`は呼ばず、`decision_evaluated`は生成されない。③〜⑤（時計前進・`decision_evaluated`非生成・イベント→例外の順序）はテストで検証する（受け入れ基準の対応項目に含まれる）。

### D4: fetchmanyのバッチサイズは実装時の裁量とする

アダプタは`row_cap`指定時、`cursor.fetchmany(n)`を`row_cap+1`行を観測するまで繰り返し、観測した時点で即座に中断する。各回のバッチサイズ`n`は残り取得枠に制限する（`n = min(チャンクサイズ, row_cap + 1 − 取得済み行数)`）。これにより`row_cap+1`行を超える行をmaterializeせず、spec「それ以降の行を取得してはならない（MUST NOT）」を1バッチの粒度でも満たす。チャンクサイズ自体は観測可能な契約に影響しない実装詳細とする。境界ケース（結果行数が`row_cap`・`row_cap+1`・バッチ境界と一致する場合）はテストで固定する。

### D5: fault-injection specへのdelta追加は不要

fault-injection spec「機械可読taxonomy（category / severity）」Requirementは既に「fault由来でない例外（介入上限超過）では両属性はNoneでなければならない」と汎用的に定めており、`on_max_rows="error"`固有の文言ではない。本changeで新設する`max_result_rows`経路の`DollyLimitError`も同一クラス・同一構築方法（`category`/`severity`を渡さない`_event`相当のイベント構築）を使うため、この既存文言がそのまま適用され、spec変更を要しない。

## Risks / Trade-offs

- [row_cap実装がバックエンドのカーソルAPI差異に依存する] → SQLite（`sqlite3.Cursor.fetchmany`）・DuckDB（`duckdb`カーソルの`fetchmany`）とも実装可能なことはissue起票時に確認済み。共通ロジックは`adapters/base.py`に置き、重複実装を避ける。
- [中断用シグナル例外がpublic APIとして誤用・誤catchされる] → `dogdb.adapters.base`内部限定とし、`dogdb.__init__`のexportに含めない。ドキュメント上も「内部制御フロー用」と明記する。
- [`max_result_rows`と`max_intervention_rows`の評価順序が直交性の誤解を招く] → `row_cap`中断はバックエンド読み取り中（アダプタ層）に発生しうるため、両方超過条件を満たす結果では`max_result_rows`側が時系列上先に判定される。これは「独立ノブ」の意味論（結合バリデーションなし・互いの設定値を参照しない）とは矛盾しないが、契約文書に評価順序として明記する。
- [`limit_exceeded.details.observed`の型がイベント種別内で不揃いになる（`max_intervention_rows`経路は整数、`max_result_rows`経路は固定文字列`"exceeded"`）] → event-log spec・contract-v2.mdに型分岐を明記し、`dolly.log()`の読み手・テストが両方の型を許容することをtasksで確認する。

## Migration Plan

1. `adapters/base.py`に中断的取得ヘルパーと内部シグナル例外を追加する（未使用時は効果なし・非破壊）。
2. `adapters/sqlite.py`／`adapters/duckdb.py`の`execute()`に`row_cap: int | None = None`を追加する。`None`（既定）では本change適用前と完全に同一の`materialize`経路を通る。
3. `core/faults.py`に`max_result_rows`向けの`limit_exceeded`イベント生成（D3の構築方法）と`DollyLimitError`送出を追加する。
4. `proxy/connection.py`の`execute()`で、D1のシグナル例外を捕捉し3のイベント生成・例外送出を呼び出す。`wrap()`に`max_result_rows: int | None = None`を追加し、指定時は正の整数であることを検証する。
5. `docs/contract-v2.md`（アダプタ契約・イベントschema v2の`limit_exceeded`語彙表）と`README.md`（限界節）を更新する。
6. 受け入れ基準を写像したテストを追加する（tasks.mdに列挙）。

ロールバックは新規引数・新規コード経路の削除で完結する（既定`None`のため、既存呼び出し側の挙動には一切影響しない）。

## Open Questions

- D3で述べた「`decide()`によるdecision_key導出」と「`FaultEngine.on_result`によるfault評価」の区別は、issue本文が明示的に述べたものではなく契約の必須フィールド表から逆算した解釈である。→ **解消（統括レビュー、2026-07-15）**: 既存コードとの突合で確定。`Decision` は `on_result` 呼び出し前に構築されており、既存の `max_intervention_rows` 超過経路も候補評価の前に当該Decisionから `limit_exceeded` を構築して早期returnする（`decision_evaluated` は出ない）。D3の解釈は既存実装の意味論と完全に一致するため、契約緩和（event-log specの再検討）は不要。
- D2で述べた`row_cap`適用スコープ（`max_intervention_rows`検査と同一）はissueの沈黙点への補完であり、issue本文の明示的決定ではない。UNKNOWN分類・素通し経路への適用が将来必要になった場合は別changeとする。
- D4のfetchmanyバッチサイズはissue未言及の実装詳細。観測可能な契約に影響しないため本designでは確定しない。
