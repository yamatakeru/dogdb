# Project's AGENTS.md

## リポジトリ概要

DogDB は DuckDB / SQLite の DB-API 接続を包み、SQL の意味論レベルで再現可能な障害を注入するテスト専用ツール。同じ seed・session・設定・入力列なら同じ障害を再現する。詳細は README.md と docs/ を参照。

## 設計原理（実装・レビューの判断基準）

- 優先順位は「決定性 ＞ 宣言表面の忠実性」（ADR-001）。これを適用した**明示的不忠実**（例: `row_factory` 非対応、行の tuple 正規化）は仕様であり、対応漏れやバグではない。
- 決定性の保証単位はセッション全体。同一 seed・session・設定・セッション先頭からの同一順序入力列・同一 sqlglot バージョンでのみ再現を保証し、部分 replay や sqlglot バージョン間の一致は保証しない。

## 検証

- テスト: `uv run pytest`
- OpenSpec change の検証: `openspec validate`

## OpenSpec 運用

- archive は main へのマージ完了後に行う。archive までが change の完了。
- 複数の change を起票して保持している場合は、実装着手前に `/opsx:update` で先行マージ済み変更（spec・コード）との整合を取り直してから `/opsx:apply` する。
- 実装をワーカーへ委譲する場合は、change の数によらず、委譲プロンプトの先頭を `/opsx:apply <change名>` にしてスキルを発火させる。

## コミット規約

- Conventional Commits ＋日本語 subject（例: `feat(examples): 公開デモをStatic Assets化`）。
