# design — fault-taxonomy

## Context

犬メタファーの障害命名（15種、`KNOWN_FAULTS`）はレビューパネルで満場一致の好評であり不変。一方、名前から機械的に分類が読めないため、テストが「サイレント破損系を全部拾う」フィルタを書けず、内部でも `proxy/connection.py` の `_ROWCOUNT_VISIBLE_FAULTS` が「語彙が閉じるまで暫定」の列挙として残る。

既存の素材:

- `docs/contract-v2.md` の fault 合成規則テーブルに classification 列がある: `failure injection` / `temporal` / `silent / shape` / `silent / value` / `silent / state` の5値。STASH のみモード分岐（error → failure injection、missing → silent / shape）。
- `openspec/specs/fault-injection/spec.md`「1操作1 fault と優先順位」に評価順の4分類（failure injection・形状変異・値変異・状態系）が既出。
- 例外の機械可読属性は `event_id` / `fault` / `phase` / `retryable` / `outcome`（素の代入、読み取り専用パターンは未導入）。
- イベントは `schema_version=2`、`from_dict` は未知キーを黙って捨てる（フィールド宣言が必須）。「表に定義されないフィールドは replay 比較対象外」（event-log spec）、「`fault_injected` の必須集合は v1 と同一」（MUST）の2契約により、任意フィールド追加は schema_version 据え置きで可能。
- パネルで severity 語彙が割れた: error / silent_corruption / delay の3値案 vs error / silent の2値案。

## Goals / Non-Goals

**Goals**

- category / severity の語彙と全 fault（モード分岐含む）対応表を本書で確定する（実装しながら決めない）。
- 注入例外に読み取り専用属性、`fault_injected` イベントに任意フィールドとして公開する。
- `_ROWCOUNT_VISIBLE_FAULTS` を taxonomy の一次定義由来へ置き換え、「provisional」を解消する。
- 新障害追加の命名基準を文書化する。

**Non-Goals**

- 犬名・例外クラス名・outcome 語彙・schema_version・decision 導出・`POLICY_VERSION` の変更。
- 既存属性の読み取り専用化、mood 係数の category 単位化。
- `_ROWCOUNT_VISIBLE_FAULTS` の集合メンバーシップの変更（挙動不変。意味づけの付与と定義場所の移動のみ）。

## Decisions

### D1: severity は3値 `error` / `silent_corruption` / `delay` を採用する

この軸の意味は「障害がどう観測されるか」: `error`＝例外として可視、`silent_corruption`＝例外なしに結果が破損、`delay`＝結果は無傷で応答時間のみ劣化。

- 2値案（error / silent）は SLOTH の置き場がない。silent に入れると「サイレント破損を全部拾う」フィルタ（この taxonomy の第一の動機）に結果無傷の SLOTH が混入し、error に入れるのは事実に反する。severity と category の合成条件（`severity=="silent" and category!="temporal"`）を常用フィルタに要求するのは、単一属性フィルタを可能にするという目的を自ら壊す。よって3値案で決着。
- `silent_corruption`（`silent` 単独ではなく）とするのは、値が自己記述的になり、grep されたテストコードだけで意味が読めるため。

### D2: category は5値 `failure_injection` / `temporal` / `shape` / `value` / `state` を採用し、severity と直交化する

この軸の意味は「何が侵されるか」: `failure_injection`＝呼び出しそのもの（要求の拒否・応答の喪失。結果は存在しない）、`temporal`＝応答時間、`shape`＝結果の行集合・順序、`value`＝結果の値・ラベル・件数報告、`state`＝時間的一貫性（stale read）。

- 語彙は contract-v2.md の classification 列の5値をそのまま昇格し、`silent /` プレフィックスを severity 軸へ分離する（新語の発明はしない）。
- contract の classification はモードで軸が混ざっていた（STASH error → failure injection）。直交化に伴い、**エラーを投げる shape 系モード（STASH error・TAIL_CHASE error）は category=`shape` / severity=`error` に再分類する**。「何が侵されるか」（行が失われる）はモードによらず同一で、モードが変えるのは観測形態だけだからである。これにより category=failure_injection は「結果自体が存在しない純粋な失敗」（BARK・GUARD_BOWL・IGNORE・NO_DROP）に純化される。
- 注意: この category は本 taxonomy の属性値であり、「1操作1 fault と優先順位」要件の評価順（契約文書の固定全順序）とは独立。評価順は一切変更しない。

### D3: 全 fault 対応表（確定・閉じた語彙）

| fault（モード） | phase | category | severity |
|---|---|---|---|
| BARK | before_execute | failure_injection | error |
| GUARD_BOWL | before_execute | failure_injection | error |
| IGNORE | before_execute | failure_injection | error |
| SLOTH | before_execute | temporal | delay |
| NO_DROP | on_result | failure_injection | error |
| STASH（error mode） | on_result | shape | error |
| STASH（missing mode） | on_result | shape | silent_corruption |
| FALSE_EMPTY | on_result | shape | silent_corruption |
| TAIL_CHASE（error mode） | on_result | shape | error |
| TAIL_CHASE（silent mode） | on_result | shape | silent_corruption |
| PAGE_HOLE | on_result | shape | silent_corruption |
| ECHO | on_result | shape | silent_corruption |
| SHUFFLE | on_result | shape | silent_corruption |
| TANGLED_LEASH | on_result | value | silent_corruption |
| CHEW | on_result | value | silent_corruption |
| WRONG_COUNT | on_result | value | silent_corruption |
| OLD_BONE | on_result | state | silent_corruption |

キーは（fault名, モード）。モードは発火時に確定している設定（`stash_mode` / `tail_chase_mode`）から引く。この表の拡張・変更は spec 変更を要する（閉じた語彙）。

### D4: 一次定義は `core/faults.py` に置き、`KNOWN_FAULTS` との一対一を機械検証する

対応表は `KNOWN_FAULTS` の隣に不変マッピングとして定義する。全 fault 名がちょうど1回（モード分岐 fault は全モード）現れることをテストで検証し、新 fault 追加時に taxonomy の付け忘れが CI で落ちるようにする。

### D5: 例外の category / severity は読み取り専用プロパティ、fault 由来でない例外は None

`DogDBError` に `category` / `severity` を読み取り専用（`@property`）で追加する。既存属性（素の代入）の読み取り専用化はスコープ外（non-goal）。`DollyLimitError` は fault 由来でない（`fault=None` の政策ガード）ため `category=None` / `severity=None` とする — `severity=="error"` フィルタが注入 fault だけを拾うことが保たれる。

### D6: イベントは `fault_injected` のみに任意フィールドとして付与する

`Event` dataclass に `category` / `severity` を任意フィールド（デフォルト None）として宣言し、`_STRING_FIELDS` に追加する。必須フィールド表（`_V2_FIELDS`）には**追加しない** — 「`fault_injected` の必須集合は v1 と同一」（MUST）と「表にないフィールドは replay 比較対象外」（MUST NOT）の2契約により、schema_version=2 据え置き・保存済みログとの replay 互換が保たれる。`treasure_returned`（STASH の後続イベント）・`decision_evaluated`・`limit_exceeded` には付与しない: 注入の発生を表すのは `fault_injected` だけであり、他種別への付与は「fault=STASH の再利用」のような既存の曖昧さを増やす。

### D7: decision key 不参加は「導出入力に含めない」ことで担保する

category / severity は decision 導出のどの入力（domain タグ・キー素材）にも加えない。contract-v2.md の決定タグ表に**追加しない**ことを明記する。検証は v3 golden 回帰テスト（`test_policy_regression.py`）が無変更で通ることによる。

### D8: `_ROWCOUNT_VISIBLE_FAULTS` は taxonomy の一次定義側へ移し、rowcount 可視性を第3の宣言的属性として閉じる

rowcount 可視性は category / severity と直交する（SHUFFLE は shape だが件数不変、WRONG_COUNT は value だが件数可視）ため、category からの述語合成では導出できない。場当たりの列挙を別の場当たりの合成で置き換えるのではなく、**taxonomy の対応表に「rowcount 可視」フラグを第3の列として宣言し**、`connection.py` はそれを参照する。集合メンバーシップは現行の5 fault（FALSE_EMPTY・TAIL_CHASE・ECHO・PAGE_HOLE・WRONG_COUNT）と同一を維持する（挙動不変が本 change の合格ゲート。STASH missing mode の除外も現行どおり — 症状は house 経由で発見可能な行退避であり、件数報告の偽装ではない）。これで「語彙が閉じるまで暫定」の条件が満たされ、provisional コメントを解消できる。メンバーシップの変更が必要になった場合は独立の change とする。このフラグはイベント・例外には公開しない（内部述語）。

### D9: 新障害の命名基準を contract-v2.md に文書化する

基準: 「**犬の行動 × 1語で結果形状が想像できる**」こと。加えて、新 fault の追加は D3 の対応表への（category, severity, rowcount 可視性）の同時登録を必須とする（D4 の一対一検証が付け忘れを CI で落とす）。

## Risks / Trade-offs

- [STASH error / TAIL_CHASE error の category が contract の classification（failure injection）から変わる] → classification 列はこれまで機械可読でなく、外部から参照する手段がなかった（今回初めて属性として公開する）。文書上の再分類のみで観測可能な互換性影響はない。contract-v2.md の表を category / severity の2列へ更新して整合させる。
- [任意フィールド追加が古い reader を壊す] → `from_dict` は宣言済みフィールドのみ拾い未知キーを捨てる設計で、v1/v2 混在読み取り要件も既存。新フィールドは replay 比較対象外のため、旧ログ・新ログの相互比較も影響なし。
- [`_ROWCOUNT_VISIBLE_FAULTS` の移動でメンバーシップが変わる事故] → 現行集合との同値をテストで固定（挙動不変ゲート）。
- [severity 3値の `delay` が将来の非遅延・非破損 fault（例: 警告のみ）に合わない] → 語彙は閉じており拡張は spec 変更を要する。その時点の change で語彙追加を審議する（いま先回りしない）。

## Migration Plan

加算的・非破壊（BREAKING なし、ADR 節不要）。イベント必須フィールド・schema_version・decision key・`POLICY_VERSION` は全て不変で、保存済みログと golden はそのまま有効。ロールバックは revert のみ。

## Open Questions

（なし — 語彙・対応表・rowcount 可視性は本書で確定。実装中の迷いは「既存イベント・decision の byte-for-byte 不変」を優先制約とする）
