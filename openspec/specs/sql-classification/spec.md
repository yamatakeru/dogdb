# sql-classification — SQL文型分類とdialect中立性

## Purpose

SQL文をSELECT/OTHER/UNKNOWNへ分類する境界規則、全バックエンド共通のdialect中立parse設定、および分類器実装（sqlglot）のバージョン管理方針を定義する。

## Requirements

### Requirement: 文型別の分類境界
SQL分類器は、次の境界に従って文型を分類しなければならない（MUST）。CTE（`WITH ... SELECT`）、およびORDER BYの有無を問わずUNION・EXCEPT・INTERSECTによる集合演算はSELECTとして分類しなければならない（SHALL）。`INSERT`/`UPDATE ... RETURNING`はOTHERとして分類しなければならない（SHALL）——RETURNING行への`on_result`介入は将来の拡張候補として契約文書に明記するにとどめ、本要件は現時点でその介入を要求しない。複文（`;`区切りで2文以上を含む入力）、PRAGMA、EXPLAIN、およびparseに失敗した文または分類器が意味を判定できないASTノードはUNKNOWNとして分類しなければならない（SHALL）。分類器は分類不能な入力に対して例外を送出してはならず（MUST NOT）、常にUNKNOWNへfall backしなければならない（MUST）。UNKNOWNに分類された文は素通しされ、スコーピング（`only_tables`／`exclude_tables`）の評価対象にならない（SHALL）。fault-injection specの「テーブル名を抽出できない文」の規則は、SELECTに分類されたがテーブル集合を抽出できなかった文（`tables=None`）に適用される。

#### Scenario: CTEはSELECT扱いになる
- **WHEN** `WITH recent AS (SELECT * FROM orders) SELECT * FROM recent` を分類する
- **THEN** 分類結果はSELECTであり、STASH・SHUFFLE等のSELECT対象障害の候補になり得る

#### Scenario: ORDER BYのないUNIONはSHUFFLE対象になり得る
- **WHEN** `SELECT id FROM a UNION SELECT id FROM b`（ORDER BYなし）を分類する
- **THEN** 分類結果はSELECTであり、トップレベルORDER BYなしと判定されSHUFFLEの候補になり得る

#### Scenario: RETURNINGはOTHER維持
- **WHEN** `INSERT INTO orders (...) VALUES (...) RETURNING id` を分類する
- **THEN** 分類結果はOTHERであり、RETURNING行への`on_result`介入は行われない

#### Scenario: 複文・PRAGMA・parse失敗は素通しのまま
- **WHEN** 複文（`SELECT 1; SELECT 2;`）、`PRAGMA table_info(orders)`、または構文的に解釈できない文を分類する
- **THEN** いずれもUNKNOWNとして分類され、`exclude_tables` 等のスコーピング設定に関わらず障害注入なしでバックエンドへ素通しされる

### Requirement: 分類器のdialect中立性
SQL分類器は、全バックエンドで単一の方言中立parse設定（sqlglotのgeneric dialect）を使わなければならない（MUST）。バックエンドごとに異なるdialectを使ってはならない（MUST NOT）——バックエンド別dialectはconformance契約（同一seed・同一SQL列に対するdecisionのバックエンド横断一致）を壊すためである。

#### Scenario: 同一SQLは両バックエンドで同一分類
- **WHEN** 同一のSQL文字列をDuckDBセッションとSQLiteセッションのそれぞれで分類する
- **THEN** 両セッションの分類結果（kind・tables・top_level_limit・top_level_offset・has_top_level_order_by）は完全に一致する

### Requirement: 分類器のバージョン管理
sqlglotへの依存は`pyproject.toml`で範囲制約（下限は採用バージョン、上限は次メジャー未満）として宣言しなければならない（SHALL）。golden fixtureは`uv.lock`が固定する単一バージョンのsqlglotの出力から生成しなければならない（SHALL）。

#### Scenario: 依存範囲が制約されている
- **WHEN** `pyproject.toml`の依存宣言を検査する
- **THEN** sqlglotの依存範囲制約（下限は採用バージョン、上限は次メジャー未満）が指定されている

#### Scenario: goldenは固定バージョンから生成される
- **WHEN** policy v4 golden fixtureを再生成する
- **THEN** `uv.lock`に記録された単一のsqlglotバージョンの出力から生成され、そのバージョンは`conn.dolly.stats()`のメタフィールドと一致する
