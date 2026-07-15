## MODIFIED Requirements

### Requirement: 分類・介入統計の参照
`conn.dolly.stats()` は、匿名fingerprint単位の分類結果（分類済みSELECT数、UNKNOWN数、介入された操作数）を構造化オブジェクトで返さなければならない（SHALL）。対応範囲外操作は理由別の素通し集計で返さなければならない（SHALL）。`allow_native_passthrough=True` のセッションでは、アダプタが宣言したSQL実行能力のある入口の呼び出し回数を入口名ごとに集計し、宣言外の転送呼び出しは集約カウンターで返さなければならない（SHALL）。集計は属性の取得時ではなく呼び出し時に行わなければならず（MUST）、`hasattr` 等による属性参照だけで計数が増えてはならない（MUST NOT）。統計に生SQL、生パラメータ、パラメータの型名、呼び出し引数を含んではならない（MUST NOT）。`stats()` のスナップショットは、診断用のメタ情報として分類器実装（sqlglot）のバージョンを1フィールド含まなければならない（SHALL）。このフィールドをdecision keyの入力に用いてはならず（MUST NOT）、イベントschemaへ影響を与えてはならない（MUST NOT）。

#### Scenario: corpusの介入率を測る
- **WHEN** アプリのクエリ列を流した後に `conn.dolly.stats()` を呼ぶ
- **THEN** fingerprintごとの分類内訳と介入数が得られ、UNKNOWN率からsqlglotでも残る素通しの実態を把握できる

#### Scenario: 属性参照だけでは計数されない
- **WHEN** `allow_native_passthrough=True` のセッションで `hasattr(conn, "cursor")` を評価し、呼び出しは行わない
- **THEN** escape hatch 集計は増加しない

#### Scenario: 診断用メタ情報としてsqlglotバージョンが分かる
- **WHEN** `conn.dolly.stats()` を呼ぶ
- **THEN** スナップショットには分類器実装（sqlglot）のバージョンがメタフィールドとして含まれ、decision keyやイベントには影響しない
