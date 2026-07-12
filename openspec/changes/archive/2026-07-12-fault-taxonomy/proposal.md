# fault-taxonomy

## Why

犬メタファーの障害命名は3モデルのレビューパネルで満場一致の好評であり維持が確定しているが、名前から severity / phase が読めず、テストコードが「サイレント破損系を全部拾う」ような機械的フィルタを書けない。内部にも同根の問題があり、`proxy/connection.py` の `_ROWCOUNT_VISIBLE_FAULTS` は「fault-taxonomy が語彙を閉じるまで暫定」と明記された場当たりの列挙のまま残っている。機械可読な分類軸を一度だけ・閉じた語彙として導入し、外部のテストフィルタと内部の述語の両方をそれに載せ替える。

## What Changes

- 注入例外（`DogDBError` とその全サブクラス）に読み取り専用属性 `category` / `severity` を追加する。
- `fault_injected` イベントに任意フィールドとして `category` / `severity` を追加する（必須フィールド集合には入れない）。
- 語彙は design 時点で閉じる（実装しながら決めない）。fault（モード分岐を含む）→ category / severity の全対応表を design.md で確定する。パネルで割れた severity 語彙（error / silent_corruption / delay 案 vs error / silent 案)も design で決着させる。
- 一次定義は `core/faults.py` に閉じた対応表として置き、`KNOWN_FAULTS` と一対一を機械検証する。
- `_ROWCOUNT_VISIBLE_FAULTS`（暫定 frozenset）を taxonomy 由来の定義へ置き換え、「provisional」コメントを解消する。rowcount 可視性は category と直交する（SHUFFLE は shape だが rowcount 不可視、WRONG_COUNT は value だが rowcount 可視）ため、扱いは design で決定する。
- 新障害追加の命名基準を文書化する: 「犬の行動 × 1語で結果形状が想像できる」こと。
- 不変条件: 犬名15種・例外クラス名8種は不変。`schema_version` は 2 据え置き（「表に定義されないフィールドは replay 比較対象外」の契約を利用。`fault_injected` の必須集合は v1 同一制約があるため必須化はできない）。category / severity は decision key に参加しない。加算的・非破壊。

### Non-goals

- 犬名・例外クラス名・outcome 語彙の変更。
- `schema_version` の引き上げ、イベント必須フィールドの変更。
- 既存属性（`event_id` / `fault` / `phase` / `retryable` / `outcome`）の読み取り専用化（新属性のみが対象）。
- mood 係数の category 単位への再編（`DEFAULT_MULTIPLIERS` は fault 個別名のまま）。
- decision 導出・POLICY_VERSION への影響。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `fault-injection`: 機械可読 taxonomy の Requirement を追加する（category / severity の閉じた語彙、例外属性・イベントフィールドとしての公開、新障害の命名基準）。「エラー型階層と実DBエラーの透過」の機械可読属性の列挙に category / severity を加える。
- `event-log`: `fault_injected` イベントの任意フィールドとして category / severity を追加する（replay 比較対象外、必須集合不変）。

## Impact

- `src/dogdb/core/faults.py`: fault →（category, severity）の閉じた対応表の一次定義（モード分岐する STASH / TAIL_CHASE は発火モードで値が分かれる）。例外送出・イベント記録経路への値の受け渡し。
- `src/dogdb/core/errors.py`: `DogDBError` に読み取り専用の `category` / `severity` を追加（全8クラスへ波及、既存属性は現状維持）。
- `src/dogdb/core/event_log.py`: `Event` への任意フィールド宣言（`from_dict` は未知キーを捨てるため宣言必須）、`_STRING_FIELDS` への追加。
- `src/dogdb/proxy/connection.py`: `_ROWCOUNT_VISIBLE_FAULTS` の解消（taxonomy 由来の定義へ置換）。
- `docs/contract-v2.md`: classification 列の正式 category への昇格、イベント任意フィールドの記載、decision タグ表に category / severity を追加しないこと（decision key 不参加）の明記、命名基準の文書化。
- `tests/`: 対応表と `KNOWN_FAULTS` の一対一検証、例外属性・イベントフィールドの検証、既存イベント期待値の不変確認。
- `openspec/specs/fault-injection/spec.md`・`openspec/specs/event-log/spec.md`: delta による要件更新。
