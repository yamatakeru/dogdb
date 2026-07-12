# DogDB contract v2

この文書は DogDB v2 の相互運用契約である。キーワード MUST / MUST NOT / SHALL は拘束要件を表す。v1 の履歴契約は `docs/contract-v1.md` に残す。

## 決定関数と fingerprint

`decision_key`、SQL template fingerprint、parameter fingerprint の定義と `POLICY_VERSION` は contract v1 から変更しない。`POLICY_VERSION` は引き続き `dogdb-v1:normalize=trim+collapse-whitespace+lowercase` である。決定性の保証単位は、同一 seed、明示した同一 session ID、同一設定、およびセッション先頭からの同一の順序付き入力列である。部分 replay の一致は保証しない。

決定キーから用途別の値を得る標準導出は次式とする。

```text
derived(tag) = SHA-256(UTF-8(decision_key + ":" + tag))
```

wall-clock、OS 乱数、Python の組み込み `hash()` を決定へ使ってはならない。各用途は次の閉じたタグまたはタグ形式を使い、異なる用途間で導出値を流用してはならない。

| tag / pattern | purpose |
|---|---|
| `fire:<FAULT>` | 障害ごとの発火判定 |
| `rows:STASH` | STASH の行位置 |
| `rows:ECHO` | ECHO の複製行位置 |
| `rows:TAIL_CHASE` | TAIL_CHASE の切り詰め行数 |
| `rows:PAGE_HOLE` | PAGE_HOLE の除去行数 |
| `perm:SHUFFLE:<index>` | Fisher–Yates の各交換位置 |
| `cell:CHEW` | CHEW の対象セル |
| `profile:CHEW` | CHEW のプロファイル選択 |
| `columns:TANGLED_LEASH` | 交換する隣接列 |
| `count:WRONG_COUNT` | logical rowcount の差分 |
| `delay:SLOTH` | SLOTH の遅延量 |
| `hold:RETURN` | RETURN_TREASURE の保持期間 |
| `stale:OLD_BONE` | OLD_BONE の参照 occurrence |
| `mood:<epoch>` | epoch ごとの mood 遷移 |
| `event:<seq>:<event-name>` | event ID |
| `treasure:<row-index>` | treasure ID |

### MVP 導出互換性

STASH / SHUFFLE / IGNORE は v1 の決定値とイベント列を維持するため、上表の対応用途を実装内の互換タグへ解決し、v1 と同じ NUL 区切り label 導出（STASH の行位置だけは decision key digest そのもの）を使う。この互換経路は既存3障害だけに閉じ、新規障害は標準のコロン区切り導出を使う。これは schema version とは独立した replay 互換性規則である。

## fault 合成規則

1操作へ適用する fault は最大1つとする。候補は次の固定全順序で評価し、前提条件を満たし、かつ発火した最初の1件だけを適用する。未指定の障害の base weight は0である。

| order | phase | classification | fault |
|---:|---|---|---|
| 1 | `before_execute` | failure injection | BARK |
| 2 | `before_execute` | failure injection | GUARD_BOWL |
| 3 | `before_execute` | failure injection | IGNORE |
| 4 | `before_execute` | temporal | SLOTH |
| 5 | `on_result` | failure injection | NO_DROP |
| 6 | `on_result` | failure injection | STASH（error mode） |
| 7 | `on_result` | silent / shape | STASH（missing mode） |
| 8 | `on_result` | silent / shape | FALSE_EMPTY |
| 9 | `on_result` | silent / shape | TAIL_CHASE |
| 10 | `on_result` | silent / shape | PAGE_HOLE |
| 11 | `on_result` | silent / shape | ECHO |
| 12 | `on_result` | silent / shape | SHUFFLE |
| 13 | `on_result` | silent / value | TANGLED_LEASH |
| 14 | `on_result` | silent / value | CHEW |
| 15 | `on_result` | silent / value | WRONG_COUNT |
| 16 | `on_result` | silent / state | OLD_BONE |

`before_execute` の failure injection が発火した場合は backend を実行しない。SLOTH は遅延後に backend 実行を続けるが、その操作の fault 枠を消費する。`on_result` は backend 実行後に評価する。

## イベント schema v2

イベントは1イベント1行の UTF-8 JSONL とする。全イベントに次のコアフィールドを必須とする。

| field | type | meaning |
|---|---|---|
| `schema_version` | integer | 常に `2` |
| `event_id` | string | 同じ replay で安定な一意識別子 |
| `session_id` | string | セッション識別子 |
| `seq` | integer | セッション内で1から欠番なく単調増加 |
| `event_type` | string | 下表のイベント種別 |

イベント種別ごとの追加必須フィールドは次のとおりである。

| event_type | required fields beyond core |
|---|---|
| `fault_injected` | `fault`, `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details` |
| `treasure_returned` | `fault`, `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details` |
| `mood_changed` | `details`（`from`, `to`, `tick`） |
| `limit_exceeded` | `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details`（`limit`, `configured`, `observed`） |
| `decision_evaluated` | `phase`, `template_fingerprint`, `parameter_fingerprint`, `occurrence`, `decision_key`, `outcome`, `details` |

`fault_injected` と `treasure_returned` は `schema_version` を除いてv1と同じ必須フィールド集合を持つ。未定義の拡張フィールド、診断用 timestamp、任意の `mood` は replay 比較の対象外とする。writer は単一プロセス・単一インスタンス契約である。reader はv1とv2の混在を受理し、未知の schema version、不正JSON、不正UTF-8、必須フィールド不足の行を警告付きでスキップする。

### warning outcome 語彙

| event_type | outcome | meaning |
|---|---|---|
| `limit_exceeded` | `fault_skipped` | 安全上限を超えたため結果を無改変で返し、fault 注入を見送った |
| `decision_evaluated` | `not_injected` | debug 評価では候補を調べたが fault は適用されなかった |

`limit_exceeded.details.limit` は現在 `max_rows`、`configured` は設定上限、`observed` は materialize された行数である。生SQL、生パラメータ、生行値をイベントへ含めてはならない。

## native passthrough と escape hatch 統計

接続proxyの未定義属性は既定で生接続へ転送せず、`AttributeError`で拒否する。`allow_native_passthrough=True`を明示した場合だけ転送を許可し、callableな属性が実際に呼ばれた時点で`stats()["escape_hatches"]`を増分する。アダプタが宣言したSQL実行能力のある入口は属性名ごとに、それ以外のcallableは`other`に集約する。属性取得や`hasattr`だけでは増分しない。また、生SQL、生パラメータ、呼び出し引数は統計に保持しない。

escape hatchの値はnative methodの**呼び出し回数**であり、backendが実行したSQL数ではない。とくにDuckDBの`sql()`は遅延評価されるrelationを返すため、`sql`の呼び出し回数と実際のSQL実行回数は一致するとは限らない。転送経路は障害注入、イベント記録、論理時計、occurrence更新の対象外である。

## SQL、scope、backend の境界

core は backend ライブラリを import してはならず、backend 由来の例外を変換してはならない。DogDB はSQLを書き換えず、分類済み操作の論理結果だけを加工する。

`only_tables` / `exclude_tables` は保守的に抽出できたトップレベル `FROM` のテーブル名へ適用する。抽出不能文は `only_tables` 指定時は対象外、`exclude_tables` 指定時は対象とする。両方のscopeを同時に指定してはならない。scope、イベント、統計へ生SQLや生パラメータを保持してはならない。
