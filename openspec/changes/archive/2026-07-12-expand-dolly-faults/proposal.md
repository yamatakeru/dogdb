# Proposal: expand-dolly-faults

## Why

`add-dogdb-mvp` は読み取り系の最小4障害でDogDBの骨格（決定性・house・イベントログ）を確立するが、fusionブラインドパネル（2026-07-11、3ワーカー全員成功）はrazorを通過する障害候補を10種以上特定しており、DogDBの差別化の核である**相関障害（mood）**と**実在障害クラスの網羅**はまだ実現されていない。パネルの検討結果が新鮮なうちに全障害のロードマップを一つのchangeとして固定し、MVP実装と並行して熟成させる。

### 改訂条項（本changeの性質）

本changeは**先行起票 `add-dogdb-mvp` の実装過程で得た知見により更新されることを前提とする**。具体的には次の実装知見が本changeのdesign/specs/tasksの内容を変更し得る:

- 保守的SQL分類器の実介入率（TAIL_CHASE / PAGE_HOLE等の行加工系の適用条件に影響）
- DuckDB/SQLiteアダプタの実測差分（TANGLED_LEASH / WRONG_COUNTの実装可否・コストに影響）
- `LogicalResult` のメモリ上限の妥当値（OLD_BONEの結果キャッシュ設計に影響）
- イベントログschema v1の運用実感（mood_changedイベント追加がv1の追加フィールドで済むかv2昇格かに影響）

このためdesign/specs/tasksは**MVP実装完了後に確定**させる。proposalの段階では障害候補の全量とスコープ境界のみを契約とする。

## What Changes

- **読み取り系障害の追加**（すべてResult House方式・結果セット加工のみ）:
  - **ECHO**（同じおもちゃを2回見せる→duplicate read delivery）。パネル3ワーカーが独立提案した、書き込み系DOUBLE_PAWの安全な代替
  - **TAIL_CHASE**（遊びの途中で帰る→truncated read / premature EOF）。部分返却後にエラーを出す変種と、静かに切り詰める変種の採否はdesignで決定
  - **FALSE_EMPTY**（「ないよ」と嘘をつく→false negative read / cache false miss）
  - **PAGE_HOLE**（ページを1枚食べた→OFFSETページングの穴）
  - **CHEW**（噛む→値破損）。任意変異ではなく具体プロファイル限定: utf8切り詰め、数値精度損失、NULL化
  - **TANGLED_LEASH**（リードが絡まる→列順・列名の取り違え / column-label drift）
  - **WRONG_COUNT**（数え間違い→rowcount改ざん / ack-count mismatch）
- **可用性・時間系障害の追加**:
  - **SLOTH**（寝たふり→slow query / プール枯渇）。注入可能clockを設計し、実時間sleepと論理遅延を分離する
  - **BARK**（吠えて近づけない→transient error）、**GUARD_BOWL**（餌皿を守る→lock timeout / database busy）。分類済み・retryableな一時エラーの決定的注入
  - **IGNOREの分割**: lost request（既存・実行前）と lost response（実行後に応答喪失、outcome="unknown"）を別障害にする
- **mood状態機械（最小版）**: seed駆動・クエリ数を論理時計とする2〜3状態（例: CALM / SLEEPY / ZOOMY）。状態が障害重みを変調し、バースト相関障害を実現する。`mood_changed` を独立イベントとして記録。wall-clockを遷移入力にしない
- **RETURN_TREASURE自動返却**: Nクエリ後にドリーが自分で宝物を返す（eventual consistencyの完成形）。返却タイミングも決定的
- **OLD_BONE**（昔埋めた骨→stale replica read）: 同一fingerprintの過去結果を返す。結果キャッシュ（容量上限・機密性設計含む）が前提
- **fault合成規則の一般化**: MVPの「1操作1 fault・failure injection優先」を、mood変調と多障害共存下でも成り立つ規則に拡張
- **設定APIの拡張**: 障害別重み、対象テーブル/クエリのスコーピング（パネル判事が指摘した公開設定APIの盲点への回答）
- **書き込み系障害の設計調査**: orphan write（実行後にエラー返却、autocommit限定・明示opt-in）の安全条件を調査する。**本changeでの成果物は設計文書であり、実装可否の判断はその結果に従う**（実装しない結論も許容する）

## Capabilities

### New Capabilities

- `mood-engine`: seed駆動の気分状態機械。論理時計、状態遷移の決定性、障害重みの変調、mood遷移イベント
- `stale-read-cache`: OLD_BONE用の過去結果キャッシュ。容量上限、機密性（生値保持の範囲）、fingerprint互換性

### Modified Capabilities

（いずれも `add-dogdb-mvp` が確立するspecへのdelta。本changeの実装開始は同specのsync後）

- `fault-injection`: 新障害群の追加、IGNOREのlost request / lost response分割、CHEWプロファイル、fault合成規則の一般化、障害スコーピング設定
- `dog-house`: RETURN_TREASURE自動返却（決定的タイミング）の追加
- `event-log`: `mood_changed` イベント種別、debugモードの非発火decisionイベント、schema versionの扱い
- `determinism`: 論理時計とmood状態を含めた決定キーの拡張（状態があっても「同一seed＋同一入力列→同一イベント列」を維持）
- `dbapi-proxy`: 設定APIの拡張表面（重み・スコーピング・注入可能clock）

## Impact

- **コード**: `add-dogdb-mvp` が作る `dogdb` パッケージへの追加。公開APIは追加的（additive）変更を原則とし、**BREAKING** な変更は現時点で予定しない（mood導入で既定挙動が変わる場合はopt-inとする）
- **依存**: 追加の実行時依存は原則なし。SQL分類の精度向上が必要になった場合の `sqlglot` 導入はdesignで判断
- **順序**: 実装は `add-dogdb-mvp` の完了・アーカイブ後。本changeのdesign/specs/tasksは改訂条項に従いその時点の知見で確定させる
- **非目標（本changeでも変わらないもの）**: ZOOMIES（スキーマ破壊）はpgwireプロキシ/Entity House以前は非目標。任意クエリ変異は恒久不採用。Entity House、pgwireプロキシ、ORM統合は本changeの範囲外
