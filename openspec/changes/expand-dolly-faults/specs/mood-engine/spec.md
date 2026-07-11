# mood-engine — seed駆動の気分状態機械

## ADDED Requirements

### Requirement: 論理時計
mood engineの時間はセッション内の論理時計でなければならない（MUST）。論理時計はプロキシへの `execute` / `executemany` 呼び出しごとに1進み（素通し文を含む）、wall-clock時刻を遷移入力に使ってはならない（MUST NOT）。

#### Scenario: 素通し文でも時は進む
- **WHEN** 分類不能な文を3回、分類可能なSELECTを1回実行する
- **THEN** 論理時計は4進んでいる

### Requirement: 決定的な状態遷移
moodは `CALM` / `SLEEPY` / `ZOOMY` の3状態を持たなければならない（MUST）。状態遷移は論理時計を固定長epoch（設定可、既定10操作）で区切ったepoch境界でのみ起こり、遷移先は `(seed, session_id, epoch番号)` から導出される決定的ハッシュのみで決まらなければならない（SHALL）。moodは既定で無効であり、無効時の障害決定はmood導入前と完全に一致しなければならない（MUST）。

#### Scenario: 同一seedなら同じ気分の推移
- **WHEN** mood有効・同一seed・同一session_id・同一クエリ列で2回実行する
- **THEN** 両実行のmood遷移列（遷移タイミングと遷移先）は完全に一致する

#### Scenario: mood無効なら何も変わらない
- **WHEN** mood設定を省略して従来と同じ障害設定でクエリ列を実行する
- **THEN** イベントログはmood機能導入前の実装と完全に一致する

### Requirement: 障害重みの変調
moodは各障害の実効重み（base重み × mood係数）のみを変調しなければならない（SHALL）。決定キーの構成やハッシュ導出をmoodで変更してはならない（MUST NOT）。mood係数表は設定で上書きできなければならない（SHALL）。

#### Scenario: SLEEPYはIGNOREを強める
- **WHEN** SLEEPY状態でIGNOREのbase重みに係数3.0が適用される
- **THEN** 発火閾値の比較にのみ実効重みが使われ、イベントの `decision_key` は従来の決定関数の出力のままである

### Requirement: mood遷移イベント
mood状態が変化したとき、`mood_changed` イベントを記録しなければならない（SHALL）。イベントは遷移前状態、遷移後状態、遷移時の論理時計値を `details` に含まなければならず（MUST）、SQLテンプレートに紐づくフィールド（template_fingerprint等）を要求されてはならない（MUST NOT）。

#### Scenario: 気分の変わり目が残る
- **WHEN** epoch境界でCALMからZOOMYへ遷移する
- **THEN** `event_type: "mood_changed"` のイベントが `details` に from / to / tick を持って記録される
