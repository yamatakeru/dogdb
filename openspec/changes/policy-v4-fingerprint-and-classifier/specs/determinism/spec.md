## ADDED Requirements

### Requirement: SQLテンプレートfingerprintの正規化
`template_fingerprint`の計算は、SQL文字列に対し次の正規化を適用した結果のSHA-256でなければならない（MUST）。単一引用符文字列リテラルの内容（`''`エスケープを含む）は保持し、変更してはならない（MUST NOT）。`--`行コメントおよび`/* */`ブロックコメントは認識して除去しなければならない（SHALL）。リテラルとコメントを除いた領域には、先頭末尾のUnicode whitespace除去、連続whitespaceの単一ASCII空白への置換、およびUnicode lowercase変換を適用しなければならない（SHALL）。引用識別子（`"..."`）の内容はlowercase変換の対象としなければならない（SHALL）——両バックエンドとも識別子は大小文字非区別であり、同一視が正しいためである。単一引用符文字列と`--`・`/* */`コメント以外の方言的クォーティング（例: `$$…$$`）は認識してはならず（MUST NOT）、通常のSQLテキストとして扱われる。リテラルとコメントの境界判定は単一の左から右への走査で行わなければならず（MUST）、リテラル外で開始したコメントのみを除去し、コメント内のアポストロフィをリテラル開始と誤認してはならない（MUST NOT）。リテラル内に現れる `--` および `/* */` をコメントとして認識・除去してはならない（MUST NOT）。

#### Scenario: リテラルの大小文字差は別テンプレート
- **WHEN** `SELECT 'DOG'` と `SELECT 'dog'` の2つのSQLをfingerprint化する
- **THEN** 2つの `template_fingerprint` は異なる値になる

#### Scenario: リテラル内空白とエスケープが保持される
- **WHEN** 内部空白と `''` エスケープを含むリテラル（例: `SELECT 'a   b'''`）をfingerprint化する
- **THEN** リテラル内容は変更されず正規化後の文字列に現れ、リテラル外の空白のみが畳まれる

#### Scenario: コメント差のみは同一テンプレート
- **WHEN** `SELECT 1 -- request-id: abc` と `SELECT 1 -- request-id: xyz` をfingerprint化する
- **THEN** 2つの `template_fingerprint` は一致する

#### Scenario: コメント内アポストロフィで誤認しない
- **WHEN** コメント内にアポストロフィを含むSQL（例: `SELECT 1 -- don't break`）をfingerprint化する
- **THEN** 正規化は破綻せず、コメントは正しく除去された結果のfingerprintが得られる

#### Scenario: リテラル内のコメント記号は除去されない
- **WHEN** リテラル内に `--` を含むSQL（例: `SELECT 'a -- b'`）をfingerprint化する
- **THEN** リテラル内容 `a -- b` はコメントとして除去されず、そのまま保持される

## MODIFIED Requirements

### Requirement: 保証の単位はセッション先頭からの入力列
決定性の保証は「セッション先頭からの同一の順序付き入力列と同一設定、かつ同一バージョンの分類器実装（sqlglot）」に対して定義されなければならない（MUST）。途中の操作単体を切り出したreplay（部分replay）の一致は保証の対象外であることを文書化しなければならない（SHALL）。異なるバージョンのsqlglotを用いた実行間でのdecision・イベント列の一致は保証の対象外であることを文書化しなければならない（SHALL）。

#### Scenario: 途中から再開しても同じにはならない
- **WHEN** 20操作のセッションの後半10操作だけを新しいセッションとして実行する
- **THEN** 論理時計とmood状態が異なるため、イベント列の一致は保証されない（これは仕様どおりの挙動である）

#### Scenario: 分類器バージョンが違えば保証対象外
- **WHEN** 異なるバージョンのsqlglotを使う2つの環境で同一seed・同一session_id・同一クエリ列を実行する
- **THEN** 分類境界の解釈差により結果が変わりうるため、decision・イベント列の一致は保証されない（これは仕様どおりの挙動であり、golden fixtureは`uv.lock`で固定した単一バージョンから生成する）
