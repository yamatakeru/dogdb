## Why

DecisionEngineにはSTASH・SHUFFLE・IGNORE専用のv1互換導出（`legacy_unit_interval` / `legacy_id`、STASH行位置のdigest直接使用、SHUFFLEのNUL区切りswap導出）が残り、determinism specも「v1互換経路を保持しなければならない（SHALL）」と要求している。この互換経路の受益者はv1時代のイベント列との一致のみであり、外部利用者ゼロ・リリース前の今、その相手はリポジトリ内のゴールデンフィクスチャ1つだけである。最初のタグ付きリリース以降はBREAKING禁止に復帰するため、今やらないと正規の移行コスト（POLICY_VERSION手続き＋移行文書）が永続する。

## What Changes

- **BREAKING**: `POLICY_VERSION` を `dogdb-v3:normalize=trim+collapse-whitespace+lowercase` に更新する。POLICY_VERSIONはdecision key・HMACキー・moodキーの導出入力であるため、全決定値・全イベント列が変わる。
- STASH・SHUFFLE・IGNOREの導出をdomain separationの正規形へ合流する: 発火判定は `fire:<FAULT>`、STASH行位置は `rows:STASH`、SHUFFLEのswapは `perm:SHUFFLE:<index>`、event ID / treasure IDは `deterministic_id`（コロン区切り）。
- `decision.py` の `legacy_unit_interval` / `legacy_id` と、`faults.py`（`_fires` / `_event` / `_stash` / `_shuffle`）・`proxy/connection.py`（`_log_return`）の互換分岐を削除する。
- determinism specの「乱数導出のdomain separation」要件から、v1互換経路の保持を求める例外文（SHALL）を削除する。
- `docs/contract-v2.md` からPOLICY_VERSION据え置きの記述と「MVP 導出互換性」節を削除し、policy v3を記載する。`docs/contract-v1.md` は削除せず「歴史的文書・policy v3で失効」とマークする。
- ゴールデンフィクスチャを**このchangeで1回だけ**再生成し、`test_mvp_compatibility.py` をv3基準線へ付け替える（決定値の意図せぬ変動を検知する回帰網としての価値は基準線が変わっても不変）。W3-b（zero-weight-fast-path）より先行することで、ゴールデンの二度作り直しを避ける。

### Non-goals

- イベントschema（`schema_version: 2`、フィールド集合、v1/v2混在ログ読み取り）の変更はしない。event-log specのv1言及はワイヤスキーマの話であり、本changeの射程外。
- ゼロ確率時のパフォーマンス改善はW3-b（zero-weight-fast-path）で扱う。導出経路の統一のみに差分を閉じる。
- fault語彙の見直しはW4-b（fault-taxonomy）で扱う。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `determinism`: 「乱数導出のdomain separation」要件からv1互換経路の例外（STASH・SHUFFLE・IGNOREのv1導出保持SHALL）を削除し、全障害が単一の正規導出形を使うことを要求する。

## Impact

- **コード**: `src/dogdb/core/decision.py`（legacyメソッド削除・POLICY_VERSION更新）、`src/dogdb/core/faults.py`（互換分岐4箇所）、`src/dogdb/proxy/connection.py`（`_log_return` の分岐）。`mood.py` はコード変更なしだがPOLICY_VERSION経由で導出値が変わる。
- **テスト**: `tests/fixtures/mvp_legacy.json` 再生成、`tests/test_mvp_compatibility.py` v3付け替え、`tests/test_mood.py` のlegacy導出参照の更新。他テストにハードコードされた実決定値はない（プレースホルダのみ）。
- **文書**: `docs/contract-v2.md`、`docs/contract-v1.md`。
- **利用者影響**: v1決定値・イベント列に依存するreplayは再現不能になる（**BREAKING**）。外部利用者はゼロ、リリース前のため破壊的変更ガバナンス（openspec/config.yaml）の通常選択肢として実施。ADR節をdesign.mdに必須で設ける。
- **依存関係**: W3-b（#8 zero-weight-fast-path）は本changeの完了が前提。
