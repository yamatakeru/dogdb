# event-log — JSONLイベントログ

## ADDED Requirements

### Requirement: スキーマv1の必須フィールド
すべての注入・返却イベントは、`schema_version`、`event_id`、`session_id`、`seq`、`event_type`、`fault`（該当時）、`phase`、`template_fingerprint`、`parameter_fingerprint`、`occurrence`、`decision_key`、`outcome`、`details` を含むJSONオブジェクトとして記録されなければならない（MUST）。

#### Scenario: STASHイベントの形
- **WHEN** STASHが発火する
- **THEN** 追記されたJSONL行は必須フィールドをすべて含み、`details` に隠した行位置が入る

### Requirement: 機密情報の既定非記録
生SQL、生バインドパラメータ、生の行値は、既定設定においてイベントログへ記録されてはならない（MUST NOT）。パラメータはHMAC化された `parameter_fingerprint` としてのみ残さなければならない（SHALL）。

#### Scenario: 機密値がログに漏れない
- **WHEN** 機密文字列をパラメータに含むクエリでSTASHが発火する
- **THEN** イベントログファイルのどの行にもその文字列が平文で現れない

### Requirement: セッション内単調シーケンス
`seq` はセッション内で厳密に単調増加しなければならない（MUST）。MVPのログライターは単一writer契約とし、複数プロセスからの同時追記は非対応であることを文書化しなければならない（SHALL）。

#### Scenario: 欠番も逆行もない
- **WHEN** 1セッションで複数の障害イベントが記録される
- **THEN** `seq` は1ずつ増加する

### Requirement: テストから参照できるイベントAPI
`conn.dolly.log()` は記録済みイベントを構造化オブジェクトの列として返さなければならない（SHALL）。JSONLファイルの出力先は設定可能でなければならない（SHALL）。読み取り側は不正なJSON行および不正なUTF-8バイト列を含む行をスキップし、警告を発しつつ残りのイベントを返さなければならない（SHALL）。

#### Scenario: テストが障害発生をassertする
- **WHEN** テストコードが `conn.dolly.log()` を呼ぶ
- **THEN** `events[-1].fault == "STASH"` のような属性ベースの検証ができる

#### Scenario: 破損行があっても読める
- **WHEN** JSONLファイルの1行が途中で切れている
- **THEN** 読み取りは警告付きでその行をスキップし、他のイベントを返す

#### Scenario: 不正なUTF-8を含む行があっても読める
- **WHEN** JSONLファイルの1行に不正なUTF-8バイト列が含まれる
- **THEN** 読み取りは警告付きでその行だけをスキップし、前後の正常なイベントを返す
