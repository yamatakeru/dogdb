## Context

DecisionEngineの導出は現在2系統ある。標準形は `SHA-256(decision_key ‖ ":" ‖ 用途タグ)`（`derive` / `unit_interval` / `deterministic_id`）だが、MVP由来のSTASH・SHUFFLE・IGNOREだけはv1の決定値を維持するため、NUL区切りの `legacy_unit_interval` / `legacy_id`（decision.py:75-85）を使い、呼び出し側に障害名による分岐が4箇所ある（faults.py `_fires` / `_event` / `_stash` / `_shuffle`、proxy/connection.py `_log_return`）。さらにSTASHの行位置はdecision key digestを直接使い、SHUFFLEのswapタグはNUL区切りの `SHUFFLE:<index>` である。determinism specはこの互換経路の保持をSHALLで要求し、contract-v2.mdは「MVP 導出互換性」節で実装内の互換タグ解決を規定している。

このv1互換の受益者は `tests/fixtures/mvp_legacy.json`（ゴールデンフィクスチャ）との一致のみ。外部利用者はゼロで、最初のタグ付きリリース前である。

## Goals / Non-Goals

**Goals:**

- 全障害の導出を単一の正規形（domain separation）へ合流し、障害名による導出分岐をゼロにする。
- `POLICY_VERSION` をv3へ更新し、決定値の世代交代を正規の識別子で宣言する。
- ゴールデンフィクスチャの再生成をこのchange内の1回で完結させる（W3-bの基準線を確定させる）。

**Non-Goals:**

- イベントschema（`schema_version: 2`）・フィールド集合・v1/v2混在ログ読み取りの変更（ワイヤスキーマは導出と独立）。
- ゼロ確率時のパフォーマンス改善（W3-b）。
- fault語彙の整理（W4-b）。

## Decisions

### D1: POLICY_VERSIONは「v2」を飛ばして `dogdb-v3` にする

contract文書v2は「POLICY_VERSIONはv1から変更しない」を明記して確定済みであり、policy「v2」を新設すると契約文書のv2と同名異義のバージョンが並ぶ。導出規則の世代（v1=NUL区切りのみ → v2=正規形とlegacy併存 → v3=正規形のみ）とも整合するため、`dogdb-v3:normalize=trim+collapse-whitespace+lowercase` とする。正規化規則自体は変更しないため、サフィックスは維持する。

### D2: 3障害の正規形マッピングは既存タグ表をそのまま実装する

contract-v2.mdの用途タグ表は既に `fire:<FAULT>`・`rows:STASH`・`perm:SHUFFLE:<index>`・`event:<seq>:<event-name>`・`treasure:<row-index>` を正規名で列挙しており、「MVP 導出互換性」節が実装内での互換タグへの読み替えを規定しているだけである。したがって本changeはタグ表を変更せず、読み替え節を削除して表どおりに実装する:

| 用途 | v1互換（削除） | v3正規形 |
|---|---|---|
| 発火判定 | `legacy_unit_interval(key, "<FAULT>")` | `unit_interval(key, "fire:<FAULT>")` |
| STASH行位置 | decision key digest直接 | `derive(key, "rows:STASH")` |
| SHUFFLE swap | `legacy_unit_interval(key, "SHUFFLE:<i>")` | `unit_interval(key, "perm:SHUFFLE:<i>")` |
| event ID | `legacy_id(key, "event:<seq>:<name>")` | `deterministic_id(key, "event:<seq>:<name>")` |
| treasure ID | `legacy_id(key, "treasure:<row-index>")` | `deterministic_id(key, "treasure:<row-index>")` |

### D3: legacyメソッドは完全削除する（deprecated温存しない）

代替案として非推奨マーク付き温存を検討したが却下。呼び出し箇所ゼロになった導出経路を残すと、決定性の監査面積（「この経路はどこからも呼ばれないか」の継続確認）だけが増える。外部利用者ゼロのため互換シムの受益者も存在しない。

### D4: ゴールデンは「v1互換の検証」から「決定値回帰の検知」へ役割を付け替える

`test_mvp_compatibility.py` の回帰網としての価値（決定値の意図せぬ変動の検知）は基準線が変わっても不変。ただし「MVP互換」という名前はv3基準線では嘘になるため、`tests/test_policy_regression.py` へ、フィクスチャは `tests/fixtures/policy_v3_golden.json` へ改名する。フィクスチャはv3実装完了後に**1回だけ**現実装の出力から再生成し、`schema_version` をv1へ書き戻す既存のハック（v2との差分吸収）は再生成時にschema_version=2のまま記録して廃止する。

### D5: mood・HMACキーへの波及はコード変更なしで受容する

`POLICY_VERSION` はparameter fingerprintのHMACキー（decision.py:29-31）とmoodキー（mood.py:66）の導出入力でもあるため、両者の値も自動的に変わる。これは「全決定値が変わる」というADR宣言の一部であり、追加のコード変更や個別互換は設けない。

## ADR: v1決定値互換の廃止

**何が壊れるか**: 全 `decision_key`・`event_id`・`treasure_id`・導出値（発火判定・行位置・順列・遅延量・保持期間・stale参照先）・mood遷移スケジュール・HMAC化parameter fingerprintが変わる。v1/v2時代に記録したイベントログと同じ列を新バージョンで再現することは不可能になる。イベントログの**読み取り**はワイヤスキーマ規則（event-log spec）に従い引き続き可能。

**なぜ設計的に妥当か**: v1互換導出は「MVPで実測・記録された決定値との連続性を守る」という当時正当な判断だった。失効した前提は受益者の存在である——外部利用者ゼロ・リリース前の現在、互換経路が守る相手はリポジトリ内のゴールデンフィクスチャ1つに縮退した。一方で維持コスト（導出2系統・障害名分岐・spec例外・契約文書の読み替え節）は恒常的に発生し、最初のタグ付きリリース以降はBREAKING禁止によりこの負債が正規の移行手続きなしには返済不能になる。

**移行方法**: 旧決定値列の再現が必要な場合は、当該バージョン（policy v1を含む最後のリリース以前）のdogdbで再生成する。リポジトリ内の唯一の依存物（ゴールデンフィクスチャ）は本change内でv3基準線へ再生成する。`docs/contract-v1.md` は歴史的文書としてマークし削除しない。

## Risks / Trade-offs

- [フィクスチャ再生成が実装バグを固定化する] 再生成は「現実装の出力＝正」とするため、v3導出の実装ミスもゴールデンに焼き込まれうる → 再生成の前提条件として、(1) 値非依存の性質テスト群（test_determinism / test_faults / test_conformance 等）が全通過していること、(2) `legacy_` への参照がsrc/testsからゼロであること（grepで機械確認）を課す。
- [SHUFFLEの縮退分岐の挙動変化] swap導出値が変わることで「恒等順列になったら先頭2行を強制swap」分岐（faults.py:502-503）の到達パターンが変わりうるが、これは仕様内の決定的挙動であり、ゴールデンが新しい値を固定する。
- [W3-bの手戻り] 本changeの完了前にW3-bへ着手するとゴールデンを二度作ることになる → wave順序（直列）で担保。

## Migration Plan

1. `decision.py`: `legacy_unit_interval` / `legacy_id` 削除、`POLICY_VERSION` をv3へ。
2. `faults.py` / `proxy/connection.py`: 障害名分岐を削除し正規形へ（D2の表どおり）。
3. `tests/test_mood.py` のlegacy参照を `unit_interval(key, "fire:<FAULT>")` へ更新。
4. determinism spec（delta）と `docs/contract-v2.md`（POLICY_VERSION・「MVP 導出互換性」節削除）、`docs/contract-v1.md`（歴史的文書マーク）を更新。
5. 性質テスト全通過とlegacy参照ゼロを確認後、ゴールデンを1回再生成し、テスト/フィクスチャをD4のとおり改名。
6. 全テスト実行。ロールバックは単一PRのrevertで完結する（データ移行なし）。

## Open Questions

（なし——W4-a/W4-bとの境界はproposalのNon-goalsで確定済み）
