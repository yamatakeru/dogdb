# dog-house — 宝物台帳（可逆的なデータの不在）

## Purpose

STASHで隠された行を宝物としてセッション内で追跡し、現在の隠し状態の一覧表示、選択的な返却、およびイベントログからの状態再構築を可能にする。

## Requirements

### Requirement: 粘着STASH
一度隠された宝物（SQLテンプレートfingerprint × 結果セット内行位置）は、セッション内で同一fingerprintのクエリを再実行しても隠れ続けなければならない（SHALL）。再実行のたびに新しい宝物が二重登録されてはならない（MUST NOT）。

#### Scenario: 返すまで治らない
- **WHEN** STASH発火後、同一クエリを3回再実行する
- **THEN** 毎回同じ行位置が欠落し、houseの宝物エントリは1件のままである

### Requirement: 宝物の返却
`conn.dolly.return_all()` は全宝物の隠し状態を解除しなければならず（SHALL）、`return_treasure(treasure_id)` は指定した宝物のみ解除しなければならない（SHALL）。返却後の再実行では該当行が結果に復帰しなければならず（MUST）、返却は `treasure_returned` イベントとして記録されなければならない（SHALL）。

#### Scenario: ドリーが宝物を返す
- **WHEN** STASHで行が隠れた状態で `conn.dolly.return_all()` を呼び、同一クエリを再実行する
- **THEN** 全行が結果に含まれ、イベントログに `treasure_returned` が記録される

### Requirement: 宝物一覧
`conn.dolly.house()` は現在ハウスにある宝物の一覧を返さなければならない（SHALL）。各エントリは treasure_id、対象のtemplate_fingerprint、行位置、隠された行の値、および隠された時点のイベントIDを含まなければならない（MUST）。隠された行の値はhouseストア（メモリ内）にのみ保持し、イベントログには書き出してはならない（MUST NOT）。

#### Scenario: ハウスの中身を覗く
- **WHEN** STASHが発火した後に `conn.dolly.house()` を呼ぶ
- **THEN** 隠された行の値を含む宝物エントリが確認できる

### Requirement: house はイベントログの射影
houseの状態（未返却の宝物集合）は、イベントログのSTASH/返却イベント列から完全に再構築できなければならない（MUST）。再構築の対象は宝物の帰属（treasure_id、template_fingerprint、行位置、イベントID）であり、隠された行の値は含まない — 行値はイベントログに記録されないため、メモリ内houseストアにのみ存在する（SHALL）。再構築結果と生きているhouse状態の一致は自動テストで検証されなければならない（SHALL）。

#### Scenario: ログからハウスを再建する
- **WHEN** STASHと部分返却が混在したセッションのイベントログを再生する
- **THEN** 再構築されたhouseの宝物集合が、ログから得られるフィールド（treasure_id、行位置、隠し状態）において実際のhouseと一致する
