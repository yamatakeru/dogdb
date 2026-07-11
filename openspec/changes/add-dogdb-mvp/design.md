# Design: add-dogdb-mvp

## Context

DogDBは空リポジトリからの新規開発。設計はfusionブラインドパネル（gpt-5.6-sol / deepseek-v4-flash / composer-2.5、判事Fable）とgrillingによる擦り合わせで確定済み。本書はその決定を実装可能な形に固定する。

前提となる制約:

- **Result House方式**: 介入できるのはクエリ文字列（読むだけ）と結果セット（加工する）のみ。SQLは改変しない。実テーブル・スキーマ・トランザクションには触れない。
- **razor**: 障害は (1) 実在する本番障害クラスに対応し (2) seed下で決定的で (3) イベントログに残るものだけ採用する。
- **テスト専用の道具**である。本番接続に向ける用途は想定しない（MVPは読み取り系のみのため破壊は起きないが、ドキュメントで明示する）。

## Goals / Non-Goals

**Goals:**

- 1日で動くMVP: STASH / SHUFFLE / IGNORE / 手動RETURN、house台帳、JSONLイベントログ、決定的replay
- DuckDBとSQLiteの両対応を、薄いアダプタ境界で実証する
- 「同一seed＋同一入力列→同一イベント列」を自動テストで保証する
- イベントスキーマ・決定関数・house意味論を**言語中立の契約**として文書化し、将来の移行路（pgwireプロキシ、他言語）を塞がない

**Non-Goals:**

proposalのNon-goals節に列挙（第二起票`expand-dolly-faults`送り、およびZOOMIES等の恒久非目標）。

## Decisions

各決定は「決定 / 理由 / 検討した代替」で記す。すべてgrilling＋パネルで確定済み。

### D1. レイヤ構成: core / adapters / proxy の3層

```
ユーザーコード
   │  conn = dogdb.wrap(duckdb.connect(), seed=42)
   ▼
[DBAPIProxy]      DB-API互換表面。conn.dolly 名前空間
   │ SQL文字列＋パラメータ
   ▼
[DogDB Core]      DecisionEngine（決定キー→FaultPlan）
   │              HouseLedger（イベントログの射影）
   │              EventLog（JSONL, append-only）
   │ execute(sql, params)
   ▼
[BackendAdapter]  DuckDB / SQLite → LogicalResult へ正規化
```

- **決定**: coreはバックエンドを知らない。障害はすべて `LogicalResult → LogicalResult` の変換または例外送出として実装する。介入は常に「論理結果セット」に対して行い、`fetchone`/`fetchmany`はその上の薄いビューとする。
- **理由**: fetch APIの呼び方で介入タイミングが揺れると決定性が壊れる（パネルworker-3の指摘）。アダプタを糊に限定することでDuckDB+SQLite両対応のコストを抑える。
- **代替**: cursorレベルでのストリーミング介入 → fetch粒度依存で決定性が複雑化するため却下。MVPは`execute`時に全件materializeする。

### D2. 決定キー（決定性の核）

```
decision_key = SHA256(
  policy_version, seed, session_id,
  template_fingerprint,   # 正規化SQLテンプレートのハッシュ
  occurrence,             # 同一fingerprintのセッション内出現回数
  phase                   # before_execute | on_result
)
```

- **決定**: バインドパラメータは既定で決定キーに**含めない**。HMAC化した`parameter_fingerprint`をイベントログに記録し（生値は記録しない）、`include_params=True`でopt-in。
- **理由**: UUID・時刻など実行ごとに変わるパラメータを含めると「同一seedなら同一イベント列」という看板保証がユーザーの書き方次第で破れる。opt-inで忠実モードの退路も残す（パネルで正面対立した論点の調停）。
- **代替**: 常に含める（worker-1/3案）→ 既定の再現性を損なう。常に含めない → 将来の高度なテストの退路を塞ぐ。
- **付則**: Python組み込み`hash()`は使わない（プロセスごとに変わる）。wall-clock時刻を決定に使わない。SQL正規化はMVPでは控えめ（空白圧縮＋小文字化程度）とし、正規化規則自体を`policy_version`に含める。

### D3. STASHの意味論: セッション内粘着

- **決定**: 一度隠された宝物（`template_fingerprint` × 結果内行位置）はhouse台帳に載り、同一クエリの再実行でも隠れ続ける。`conn.dolly.return_all()` / `return_treasure(id)` で解除されるまで治らない。
- **理由**: houseを「ただのログ」ではなく本物の状態にする。「治るまで見えないreplication lag」の忠実な模型になり、返却操作に意味が生まれる。返却は「隠し状態の解除」なので、worker-1が警告した「無関係なSELECTへの行混入」問題は構造的に起きない。
- **代替**: 実行ごと独立 → houseが形骸化しrazor第3条件の価値が薄れるため却下。自動返却 → 第二起票へ。
- **明示する制約**: 行同一性は**結果セット内位置**であり主キーではない。パラメータが変わると同じ位置でも別の行を指し得る。この距離はEntity House導入まで残ると仕様に明記する。

### D4. 障害の2分類と配送規則

| 分類 | 障害 | 配送 |
|---|---|---|
| silent mutation | STASH（行欠落モード）、SHUFFLE | 結果が変わるだけ。例外なし。ログには残る |
| failure injection | STASH（エラーモード）、IGNORE | `DogDBError`系例外を送出 |

- **決定**: 1操作につき最大1 fault。優先順位は failure injection > silent mutation（決定キーで両方が発火候補になった場合）。
- **理由**: 判事が指摘した盲点（fault合成規則の欠落）への最小の回答。合成の一般規則は第二起票で扱う。

### D5. エラー型階層

```
DogDBError(Exception)          # 基底。機械可読属性を持つ
├── DollyStashedError          # STASH エラーモード
├── DollyIgnoredError          # IGNORE（timeout模擬）
└── （第二起票で拡張）

属性: event_id, fault, phase, retryable, outcome
  outcome ∈ {not_executed, read_partial, ...}
  IGNORE は outcome="not_executed", retryable=True
```

- **決定**: 楽しい文章（`Dolly took row #7 to her house.`）は`str(error)`のみに置き、テストの制御は属性で行う。実DBエラーはラップせず素通しし、`isinstance(e, DogDBError)`で注入と実障害を判別可能にする。
- **代替**: 実DBエラーもラップ → 透過性が下がりデバッグを阻害。透過モード（注入エラーを実DB例外に偽装）は第二起票以降。

### D6. イベントログ: JSONL、単一writer、機密性既定

スキーマv1の必須フィールド:

```json
{"schema_version": 1, "event_id": "...", "session_id": "...",
 "seq": 42, "event_type": "fault_injected",
 "fault": "STASH", "phase": "on_result",
 "template_fingerprint": "sha256:...", "parameter_fingerprint": "hmac:...",
 "occurrence": 3, "decision_key": "sha256:...",
 "outcome": "rows_hidden", "details": {"row_indices": [7]}}
```

- **決定**: 生SQL・生パラメータ・生の行値は既定で記録しない。`seq`はセッション内単調。MVPは単一writer契約（複数プロセス追記は非対応と明記）。wall-clock `ts`は診断用に記録してよいがreplay判定に使わない。STASHされた行の値はログではなく**houseストア（メモリ内）**に保持する。
- **理由**: ログが機密データの複製場所になる問題（worker-1指摘）の回避。event sourcingの真実はイベント列で、houseはその射影。
- **代替**: 全decisionイベント（非発火含む）の記録 → 既定は発火のみ、debugモードで拡張（第二起票扱いでよい）。

### D7. SQL分類は保守的に

- **決定**: SHUFFLEの対象は「トップレベルにORDER BYのないSELECT」と分類できた文のみ。STASHの対象はSELECTと分類できた文のみ。分類不能な文（CTE、複文、PRAGMA等の判定困難ケース）は**無介入で素通し**。
- **理由**: 正規表現分類はCTE/RETURNING/複文で破綻する（worker-1指摘）。誤分類で壊すより、介入率が下がる方を選ぶ。分類器の精度向上は実装知見として第二起票へ還流する。
- **代替**: sqlglot導入 → MVPには過剰。Entity House段階で本命。

### D8. 対応範囲の割り切り

- `execute` / `fetchall` / `fetchone` / `fetchmany` のみ。`executemany`は無介入素通し。
- 位置パラメータのみ（named paramの方言差回避、worker-2の割り切りを採用）。
- トランザクション（BEGIN/COMMIT/ROLLBACK）は素通し。MVPの障害は全て読み取り系なのでTX整合性と衝突しない。
- アダプタ契約は4メソッド程度に抑える: `execute(sql, params) -> LogicalResult`、`close()`、`in_transaction`プロパティ（MVPはダミー実装可、界面だけ確保）。

### D9. ブートストラップ

- git init（`.gitignore`に `.fusion-runs/`、`.venv/`、`__pycache__/` 等）、uvプロジェクト、MIT LICENSE、Python 3.12+、PyPI名`dogdb`（空き確認済み）。
- 実装はCodexへ委譲し、CodeRabbitレビューを最低一度、simplify検討を実施（AGENTS.md準拠）。

## Risks / Trade-offs

- [結果位置ベースの行同一性が「replication lag」の比喩から乖離] → 仕様とREADMEに限界を明記。Entity House（将来）で解消。それまでSTASHの実障害対応は「一時的な結果欠落」と控えめに主張する。
- [全件materializeによるメモリ圧] → MVPはテスト用途の小データ前提と明記。行数上限の設定値だけ用意し、超過時は無介入素通し＋警告イベント。
- [SQL分類の偽陰性（介入されるべき文がされない）] → 保守的分類は意図的選択。介入率はイベントログで観測可能なので、実装後に分類器の精度を測り第二起票へ反映。
- [JSONL追記の破損（プロセスkill時）] → 単一writer＋行単位追記で被害を1行に限定。読み取り側は不正行をスキップして警告。
- [DuckDBとSQLiteの`description`/`rowcount`意味差がアダプタへ漏れる] → 共通適合テストスイート（同一シナリオを両アダプタで実行）で差を検出・封じ込め。
- [粘着STASHのメモリ保持（houseストア）が長寿命セッションで肥大] → テスト用途では実害が小さい。house容量の上限と警告のみ用意。

## Migration Plan

新規プロジェクトのため移行はなし。ロールバックはgit revertで足りる。PyPI公開は本changeの範囲外（公開前にREADME・メタデータを整えてから別途判断）。

## Open Questions

実装中に答えが出る想定の未確定事項（第二起票の更新材料）:

- DuckDB Python APIとsqlite3の`cursor.description`差分の実測（アダプタ正規化コードの実量）
- 保守的SQL分類器の実介入率（SELECT判定の再現率）
- `LogicalResult`のメモリ上限の妥当な既定値
- house再構築テスト（ログ→射影一致）の粒度: イベント全種を対象にするか、STASH/RETURNのみか
