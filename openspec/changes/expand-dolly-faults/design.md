# Design: expand-dolly-faults

## Context

`add-dogdb-mvp` はcore（DecisionEngine / HouseLedger / EventLog）、薄いアダプタ境界、契約文書（docs/contract-v1.md）を確立し、アーカイブ済みである。本designはproposalの改訂条項に従い、MVP実装知見（archive/2026-07-11-add-dogdb-mvp/implementation-notes.md）を反映して確定させたものである。

反映した実装知見:

1. **SQL分類器**: quote/comment/括弧深度のみの小型lexerで代表12文中8文を分類（66.7%）。CTE / PRAGMA / EXPLAIN / 複文はUNKNOWN（意図どおり保守的）。→ 新障害も「分類できた文のみ」の境界を継承し、parser導入はcorpus計測後に判断する。
2. **アダプタ差分**: SELECTのrowcountは両バックエンドで非互換のため、materialize後の行数を logical rowcount とした。→ WRONG_COUNTはこのlogical rowcountの改ざんとして閉じ、backend rowcountには触れない。TANGLED_LEASHも `LogicalResult.columns` の加工で閉じる。
3. **メモリ上限**: 既定は1結果10,000行・house 1,000宝物。行数はbyte防御ではない。→ OLD_BONEキャッシュには独立の容量上限と決定的退避を設計する。houseのLRU自動退避は導入しない（自動返却は退避ではなく「決定的タイミングの返却イベント」）。
4. **schema v1運用感**: 全イベント種別に全フィールド必須の契約は、`treasure_returned` で既に窮屈だった（元のoccurrence等をtreasureへ保持して埋めた）。→ `mood_changed` はfingerprintを持ち得ないため、イベント種別ごとの必須フィールド表を持つ **schema v2** へ昇格する。

前提制約はMVPと同じ: Result House方式（SQLは改変しない、結果セットのみ加工）、razor（実在障害クラス・seed決定性・イベント記録の3条件）、テスト専用。

## Goals / Non-Goals

**Goals:**

- 読み取り系・可用性系・時間系の障害群を、1つの一般化された合成規則の下に追加する
- mood状態機械（opt-in）でバースト相関障害を実現し、既定挙動は一切変えない
- RETURN_TREASURE自動返却とOLD_BONE（stale read）で「時間とともに変わる嘘」を導入する
- イベントschema v2（イベント種別ごとの必須フィールド表）と契約文書v2を確定する
- 障害重み・スコーピングの設定APIを追加する（すべてadditive）

**Non-Goals:**

- 書き込み系障害の実装（orphan write調査は設計文書のみが成果物。実装しない結論も許容）
- ZOOMIES（スキーマ破壊）、任意クエリ変異、Entity House、pgwireプロキシ、ORM統合（proposalの非目標を継承）
- houseのLRU自動退避、`max_result_bytes` の厳密なbyte防御（概算計測の検討はOpen Questionsへ）
- streaming介入（全件materialize方式を維持）

## Decisions

### D1. 障害の全量と分類

| 分類 | 障害 | 実在障害クラス | phase |
|---|---|---|---|
| failure injection | BARK | transient error（一時的な接続失敗） | before_execute |
| failure injection | GUARD_BOWL | lock timeout / database busy | before_execute |
| failure injection | IGNORE（既存） | lost request | before_execute |
| failure injection | STASHエラーモード（既存） | read failure | on_result |
| failure injection | NO_DROP | lost response（実行済み・応答喪失） | on_result |
| silent（形状） | STASH行欠落（既存） | replication lag（粘着） | on_result |
| silent（形状） | FALSE_EMPTY | false negative read / cache false miss | on_result |
| silent（形状） | TAIL_CHASE | truncated read / premature EOF | on_result |
| silent（形状） | PAGE_HOLE | OFFSETページングの取りこぼし | on_result |
| silent（形状） | ECHO | duplicate read delivery | on_result |
| silent（形状） | SHUFFLE（既存） | 暗黙順序依存 | on_result |
| silent（値） | TANGLED_LEASH | column-label drift | on_result |
| silent（値） | CHEW | 値破損（閉じたプロファイル） | on_result |
| silent（値） | WRONG_COUNT | ack-count mismatch | on_result |
| silent（状態） | OLD_BONE | stale replica read | on_result |
| temporal | SLOTH | slow query | before_execute |

- **決定**: lost response の障害名は **NO_DROP**（取ってきたボールを渡さない犬）とする。IGNOREは既存名のまま lost request 専用に残す（specは既に「IGNORE（lost request）」へ改名済みなので、追加のみで分割が完成する）。
- **理由**: 全障害が犬の行動語彙で統一され、IGNOREの既存セマンティクスを壊さない。
- **代替**: IGNOREにモード追加 → 既存設定の意味が変わるため却下。

### D2. fault合成規則の一般化: 「1操作1 fault」を維持し、固定優先順位表に拡張

- **決定**: 1操作につき最大1 faultの規則を維持する。評価はphase順（before_execute → 実行 → on_result）。before_executeでfailure injectionが発火したら実行しない（SLOTHのみ例外: 発火しても遅延後に実行を続行し、その操作のfault枠を消費する）。各phase内の候補は契約に記載する固定の全順序（failure injection > 形状 > 値 > 状態 > temporal、同分類内は表の記載順）で評価し、最初に発火した1つだけを適用する。
- **理由**: 多障害共存とmood変調の下でも決定性と可読性を保つ最小の規則。スタッキング（SHUFFLE+CHEW等）はイベント解釈と決定性検証を複雑にする割に、実障害クラスの忠実度を上げない。
- **代替**: 障害の重ね掛け → 却下（上記）。phaseなしの単一抽選 → lost request/lost responseの意味区別（バックエンド状態が変わるか）を破壊するため却下。
- **付則**: 前提条件を満たさない障害（OFFSETなしのPAGE_HOLE、キャッシュ未蓄積のOLD_BONE、対象セルのないCHEW等）は候補にならない。前提条件はすべて入力列の決定的関数である。

### D3. mood状態機械: opt-in・論理時計駆動・重み変調のみ

- **決定**: 状態は CALM / SLEEPY / ZOOMY の3つ。論理時計は「セッション内の `execute` / `executemany` 呼び出し連番」（素通し文も刻む）。tickを固定長epoch（既定10操作、設定可）で区切り、epoch境界でのみ `(seed, session_id, epoch番号)` から導出したハッシュで遷移する。moodは各障害の実効重み（base重み × mood係数表）だけを変調し、決定キーやハッシュ導出には一切関与しない。既定は無効（opt-in）で、無効時の挙動はMVPと完全一致する。
- **理由**: mood状態が入力列の純粋関数になり、「同一seed＋同一入力列→同一イベント列」の看板保証がそのまま延びる。重み変調に限定することで、mood導入後もイベントの `decision_key` は従来どおり検証可能。
- **代替**: wall-clock遷移 → razor違反で恒久却下。クエリ内容依存の遷移（エラー率で興奮等）→ フィードバックループが決定性検証を難しくするため次版以降。4状態以上 → 係数表の説明可能性が落ちるため3状態で開始。
- **既定係数表**（設定で上書き可）:

| mood | 強まる障害（×3.0） | 弱まる障害（×0.5） |
|---|---|---|
| CALM | なし（全×1.0） | なし |
| SLEEPY | IGNORE, SLOTH, NO_DROP, GUARD_BOWL | SHUFFLE, ECHO, TAIL_CHASE |
| ZOOMY | SHUFFLE, ECHO, TAIL_CHASE, CHEW | IGNORE, SLOTH |

- 遷移時は `mood_changed` イベント（from / to / tick）を記録する。

### D4. イベントschema v2: イベント種別ごとの必須フィールド表

- **決定**: `schema_version: 2` へ昇格する。コアフィールド（`schema_version` / `event_id` / `session_id` / `seq` / `event_type`）は全イベント必須。それ以外はイベント種別ごとの必須フィールド表で定義する: `fault_injected` と `treasure_returned` はv1と同一のフィールド集合（互換）、`mood_changed` は `details` に from / to / tick を持ちfingerprint系フィールドを持たない、`limit_exceeded`（警告）は対象上限と観測値を持つ。読み取り側はv1行とv2行を両方受理する。契約文書は `docs/contract-v2.md` として改訂する（v1は履歴として残す）。
- **理由**: 実装知見4のとおり「全イベント全フィールド必須」はv1の時点で既に破綻の兆候があった。nullableの暗黙運用より、種別ごとの表で明文化する方が監査と実装の両方に効く。
- **代替**: v1のまま追加フィールドで済ませ、fingerprint系へnullを許す → contract-v1の「全フィールド必須」と矛盾し、既存readerの前提を静かに壊すため却下。
- **付則**: mood有効時、`fault_injected` に任意フィールド `mood` を追加してよい（診断用。replay比較には使わない、timestampと同格）。`POLICY_VERSION`（`dogdb-v1:normalize=...`）は据え置く — 決定キーの式・正規化規則は変わらず、既存構成での決定は1bitも変わらないため。

### D5. 乱数導出のdomain separation

- **決定**: 障害ごとの確率判定・行位置・順列・遅延量・保持期間など、決定キーから導く値はすべて `SHA-256(decision_key ‖ ":" ‖ 用途タグ)` で導出し、用途タグの一覧（`"fire:STASH"`, `"rows"`, `"perm"`, `"delay:SLOTH"`, `"hold:RETURN"` 等）を契約v2に列挙する。
- **理由**: 障害が16種に増えると、導出の衝突（同じハッシュを2用途で使う）が「独立なはずの障害が常に共起する」バグを生む。MVPの導出は既にこの形に近く、タグ表の明文化はadditive。
- **代替**: 障害ごとに副seedを持つ → 設定面が増えるだけで決定性上の利点がない。

### D6. 新障害のセマンティクス要点

- **ECHO**: 決定キー由来の1行を直後に複製する。`outcome="rows_duplicated"`。
- **TAIL_CHASE**: STASHと同型の2モード。silentモードは末尾k行を切り詰め `outcome="rows_truncated"`。エラーモードは `DollyTailChaseError`（`outcome="read_partial"`、届いた行数はdetailsに記録）。モードは設定で選ぶ。非粘着（houseに入らない）。
- **FALSE_EMPTY**: 列は保ったまま0行を返す。`outcome="empty_result"`。非粘着 — false missは再試行で治り得る嘘であり、粘着させるとSTASH（治るまで見えない）と区別がなくなる。
- **PAGE_HOLE**: 分類器がトップレベルの `LIMIT`/`OFFSET`（リテラル、OFFSET>0）を検出できた文だけが対象。ページ先頭の行を落とす。`outcome="page_hole"`。
- **CHEW**: 閉じたプロファイル集合 `{utf8_truncate, precision_loss, nullify}` のみ。対象セルは適合型のセルから決定キーで選ぶ。適合セルがなければ候補にならない。detailsは行番号・**列番号**・プロファイル名のみ（列名・値は記録しない）。
- **TANGLED_LEASH**: `LogicalResult.columns` の隣接2ラベルを入れ替える（値は動かさない = label drift）。detailsは列番号ペア。
- **WRONG_COUNT**: logical rowcountのみを±k（既定±1、下限0）改ざんする。行データは不変。backend rowcountには触れない。
- **BARK / GUARD_BOWL**: いずれも `retryable=True`・`outcome="not_executed"` のtransient系。BARKは接続系一時エラー、GUARD_BOWLはbusy/lock timeoutの物語と型（`DollyBarkError` / `DollyBusyError`）で区別する。
- **NO_DROP**: バックエンドで実行**完了後**に `DollyNoDropError`（`outcome="response_lost"`, `retryable=True`）を送出する。本changeでは分類済みSELECTのみ対象（読み取りの再試行は安全）。書き込みへの適用（orphan write）はD10の調査に委ねる。
- **SLOTH**: 遅延量は決定キーから導出し、必ずdetailsに `delay_ms` を記録する。実sleepは注入可能clock経由でのみ行う（D7）。

### D7. 注入可能clock: 論理遅延と実時間の分離

- **決定**: `wrap(..., clock=...)` でsleep関数を注入できるようにする。既定は実 `time.sleep`。決定（遅延量の導出・イベント記録）は論理値のみで完結し、clockは「その論理遅延を体感させるか」だけを担う。テストはno-op clockで遅延0秒のまま `delay_ms` をassertできる。
- **理由**: razorの「wall-clockを決定に使わない」を守ったままslow queryを再現する唯一の構図。CI時間を浪費しない。
- **代替**: 実sleepのみ → テスト不能。asyncio対応 → DB-API同期表面の範囲外、将来検討。

### D8. RETURN_TREASURE自動返却

- **決定**: opt-in設定 `auto_return`（保持期間の範囲を論理操作数で指定）。STASH発火時に決定キーから保持期間Nを導出し、論理時計がN進んだ最初の操作の**冒頭**（phase評価前）で自動返却する。イベントは `treasure_returned`、`phase="auto_return"`（phase語彙に追加）。手動 `return_all()` / `return_treasure()` は従来どおり優先して使える。
- **理由**: 「いつか治るreplication lag」の完成形。返却タイミングを操作冒頭に固定することで、seq順（返却→当該操作のfault）が決定的になる。
- **代替**: wall-clock保持期間 → 却下（razor）。houseのLRU退避と統合 → 退避は状態の喪失、返却は観測可能なイベントであり意味が異なるため統合しない。

### D9. stale-read-cache と OLD_BONE

- **決定**: セッション内メモリキャッシュに、fingerprint（`include_params=True` 時はparameter fingerprintも鍵に含む）ごとの**配達済み結果**（クライアントが実際に見た行列）をoccurrence番号付きで保持する。OLD_BONEは同一鍵に過去エントリがある場合のみ候補になり、決定キーで選んだ過去occurrenceの結果をそのまま返す。`outcome="stale_read"`、detailsは `stale_occurrence` のみ。容量はfingerprintごとにK件のリングバッファ＋全体上限（既定: K=4、全体64エントリ、1エントリはresult行上限に従う）。退避は挿入順で決定的。生の行値はhouse同様メモリのみでログへは書かない。
- **理由**: 「stale replicaが返すのは、かつて正しかった結果」という忠実度を、配達済み結果の再演でそのまま得る。決定性はキャッシュ内容が入力列の純粋関数であることから従う。
- **代替**: 実行前結果（fault適用前）をキャッシュ → クライアントが見たことのない結果が「過去の結果」として返り、比喩が壊れるため却下。ディスク永続化 → 機密性と単一writer契約を複雑にするため却下。

### D10. 書き込み系（orphan write）は調査文書のみ

- **決定**: 成果物は `docs/orphan-write-investigation.md`。NO_DROPを書き込み文へ拡張する安全条件（autocommit限定・明示opt-in・トランザクション内禁止・検証可能な事後観測手段）を調査し、実装可否を結論づける。「安全に実装できない」という結論も正式な成果として受理する。
- **理由**: proposalの契約どおり。実行後エラーは唯一「バックエンド状態が変わったのに失敗が返る」障害であり、テストDBであっても誤用リスクの評価が先。

### D11. 設定APIとスコーピング

- **決定**: `wrap()` に (1) 全障害の重み辞書（既存 `faults` の拡張、未指定は0）、(2) `mood` 設定（有効化・epoch長・係数表）、(3) `auto_return` 設定、(4) `clock`、(5) スコーピング `only_tables` / `exclude_tables` を追加する。スコーピングは分類器のFROM句テーブル名抽出（保守的）に基づき、抽出できない文は `only_tables` 指定時は**対象外**（安全側）、`exclude_tables` 指定時は**対象**とする。すべてadditiveで、既定値はMVP挙動と完全一致。
- **理由**: パネル判事が指摘した公開設定APIの盲点への回答。抽出不能時の非対称な既定は「介入しすぎない」方向に倒す保守的分類の原則の延長。
- **代替**: SQL述語コールバック → ユーザー関数の純粋性を保証できず決定性の責任境界が曖昧になるため見送り（Open Questionsに残す）。

### D12. 分類統計と parser 導入判断

- **決定**: `conn.dolly.stats()` で、匿名fingerprint単位の分類結果（SELECT分類数 / UNKNOWN数 / 介入数）を参照できるようにする。実アプリcorpusでUNKNOWN率（特にCTE）が支配的と計測されたときに初めてsqlglot導入を別changeで起票する。本changeの分類器拡張はLIMIT/OFFSET検出とFROMテーブル名抽出の2点のみで、いずれも既存lexerの保守的延長とする。
- **理由**: 実装知見1の還流。生SQLを集めずに介入率を観測できる（razorの機密性原則と整合）。

## Risks / Trade-offs

- [障害16種×mood係数で設定空間が説明困難になる] → 既定は全障害weight 0・mood無効。READMEには「1障害ずつ足す」導線とプリセット例のみ置く。
- [mood有効時、1操作の決定が過去の操作数に依存し「操作単位のreplay」ができない] → 看板保証は「セッション先頭からの同一入力列」であることをdeterminism specに明文化。部分replayは非目標と明記。
- [stale cacheが行値を保持しメモリを消費する] → 容量上限（D9）と、house同様「テスト用途・セッション内」の明記。上限超過時はキャッシュせずOLD_BONE候補から外れるだけ（決定的）。
- [PAGE_HOLE/スコーピングの分類器拡張が偽陽性を生む] → 検出できた場合のみ発火の原則を維持。分類器の単体テストを方言ケース（quoted identifier等）まで広げる。
- [schema v2で既存readerが壊れる] → readerはv1/v2両受理。writerがv2を書くのは本change導入後の新セッションのみ。イベント種別表はcontract-v2に固定。
- [TAIL_CHASEエラーモードとNO_DROPの区別が紛らわしい] → 前者は「部分的に届いた」（詳細に届いた行数）、後者は「全部実行されたが何も届かない」。エラー型・outcome語彙・文書で明確化する。
- [SLOTHの実sleepがCIを遅くする] → 既定clockでも遅延上限を設定必須にし、テストはno-op clockを注入。

## Migration Plan

追加はすべてopt-in・additiveで、既存ユーザーの挙動変更はない。手順: (1) schema v2 writer/reader と contract-v2 を先に入れる（既存イベント種別はフィールド互換）、(2) 合成規則の一般化とdomain separationタグ表、(3) 障害群を分類ごとに追加、(4) mood / auto-return / OLD_BONE の状態系、(5) 設定API・stats。各段階で共通適合スイート（DuckDB/SQLite一致）を拡張する。ロールバックはgit revertで足りる。

## Open Questions

- corpus計測でCTEが支配的だった場合のsqlglot導入判断（別change起票の閾値をどこに置くか）
- `max_result_bytes` の概算計測を入れるか（行数上限で実用上足りている間は見送り）
- スコーピングのSQL述語コールバック（決定性の責任をユーザーに移す明示規約を作るか）
- moodのフィードバック遷移（エラー観測で興奮する等）をv3で入れるか
- イベントログのfile rotationとsession混在時のseq検証（実装知見4の残件。本changeでは扱わない）
