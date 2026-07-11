# stale-read-cache — OLD_BONE用の過去結果キャッシュ

## ADDED Requirements

### Requirement: 配達済み結果のキャッシュ
OLD_BONEが有効なセッションでは、分類済みSELECTの**配達済み論理結果**（クライアントが実際に受け取った列名と行列）を、テンプレートfingerprint（`include_params=True` の場合はパラメータfingerprintも鍵に含む）とoccurrence番号を付してセッション内メモリへ保持しなければならない（SHALL）。キャッシュされた生の行値はイベントログへ書き出してはならない（MUST NOT）。

#### Scenario: 過去の配達結果が手元に残る
- **WHEN** 同一SELECTを2回実行し、1回目にSTASHで1行欠けた結果が配達される
- **THEN** キャッシュのoccurrence=1エントリは4行（欠けた後の配達結果）であり、その行値はログファイルに現れない

### Requirement: 容量上限と決定的退避
キャッシュはfingerprintごとのエントリ数上限と全体上限を持たなければならない（MUST）。上限到達時の退避は挿入順（最古から）で行い、退避の順序と結果は入力列のみから決定されなければならない（SHALL）。1結果の行数上限を超える結果はキャッシュしてはならず（MUST NOT）、その場合も挙動は決定的でなければならない（MUST）。

#### Scenario: あふれたら最古の骨から捨てる
- **WHEN** fingerprintごとの上限Kを超えてK+1回目の結果が配達される
- **THEN** 最古のoccurrenceのエントリだけが退避され、同一入力列の再実行でも同じ退避が起こる

### Requirement: OLD_BONEへの供給
OLD_BONEは、同一鍵の過去エントリがキャッシュに存在する場合のみ発火候補になることができる（SHALL）。発火時は決定キーから選ばれた過去occurrenceの配達済み結果をそのまま返し、イベントの `details` には参照した `stale_occurrence` のみを記録しなければならない（MUST）。過去エントリが存在しない操作でOLD_BONEを発火させてはならない（MUST NOT）。

#### Scenario: 昔埋めた骨を掘り出す
- **WHEN** 同一SELECTの3回目の実行でOLD_BONEが発火する
- **THEN** 1回目または2回目の配達結果と同一の結果が返り、イベントに `outcome: "stale_read"` と `stale_occurrence` が記録される

#### Scenario: 初回実行では骨がない
- **WHEN** セッションで初めてのSELECTを実行する
- **THEN** OLD_BONEは発火せず、他の障害決定は通常どおり行われる
