# passthrough-observability — Proposal

GitHub issue: [#22](https://github.com/yamatakeru/dogdb/issues/22)（統括: [#19](https://github.com/yamatakeru/dogdb/issues/19)）

## Why

README は「理由別の匿名素通し件数」を `conn.dolly.stats()` の契約として謳うが、現実装が理由別に記録するのは `unsupported_parameter_type` のみ（`connection.py:143-144` が唯一の呼び出し箇所）であり、名前付きパラメータ・分類不能SQL・トランザクション文は理由別に残らず、`executemany` 経路（`connection.py:242-246`）は分類記録すらしない。「フォールト注入したつもりが実は素通りしていた」という罠を利用者が観測で気づく手段が、記述と実装で乖離している。

## What Changes

- `conn.dolly.stats()` の素通し集計（`passthrough`）に、正規語彙5種すべてを記録する: `unsupported_parameter_type`（既存）・`named_parameters`・`unknown_sql`・`transaction_statement`・`executemany`（いずれも新規記録）。記録は `on_passthrough` の設定値に関わらず常に行う。
- `wrap()` に省略可能な引数 `on_passthrough: str = "allow"`（許容値 `"allow"` / `"warn"` / `"error"`）を追加する。命名は既存 `on_max_rows` と対称。
  - `"warn"`: 発火対象の素通しが起きるたびに DogDB 固有カテゴリ `DollyPassthroughWarning` で `warnings.warn` する。
  - `"error"`: 発火対象の素通しをバックエンド実行前に検出し、非retryableの `DollyPassthroughError` を送出する（実行後に構造化例外で怒るのは「素通しは無介入で実行を継続する」という既存契約と矛盾するため、実行前に止める）。
  - 発火対象は `unknown_sql`・`named_parameters`・`unsupported_parameter_type` の3種に固定する（利用者が「注入対象」と誤認しやすい理由）。`transaction_statement`（構造的に介入不能な正常運転）と `executemany`（README限界節で対象外と宣言済みの表面。含めるとORMのbulk insertが警告まみれになる）は対象外とし、これら2種は `on_passthrough` の値に関わらず常に無警告・無エラーで素通しする。
- `conn.dolly.stats()` のsnapshot形状はキー追加のみで後方互換を保つ（既存キーの削除・改名なし。`passthrough` 辞書は発生した理由キーのみを持つ既存のsparse形状を維持する）。
- README の「理由別の匿名素通し件数」記述を実装と一致させ、素通し理由の正規語彙表と `on_passthrough` の説明を追記する。
- mood／自動返却の論理時計が素通し操作でも前進する既存意味論、および素通し操作がdecision・イベントを生成しない既存契約は不変（`on_passthrough="error"` で発火対象がブロックされる場合も、この操作は元々イベントを生成しない対応範囲外操作のままである）。

副次効果として、W6-1（sqlglot導入、issue #20）完了後は `unknown_sql` の集計値が「sqlglotを導入してもなお残る分類の穴」の事後検証指標になる（統括issue #19に記載のQ1折衷案）。この意味変化は順序依存ではなく、両changeは独立に実装・マージできる。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `dbapi-proxy`: 「対応範囲外操作の素通し」Requirementを改訂し、正規語彙5種すべての理由別記録（`executemany` 経路を含む）を規定する。「分類・介入統計の参照」Requirementを改訂し、素通し集計の理由語彙が閉じた5種であることとsnapshotの後方互換（キー追加のみ）を明記する。新規Requirementとして、`on_passthrough` の3モード・発火対象3種・除外2種・`DollyPassthroughWarning`／`DollyPassthroughError` の意味論を追加する。

## Impact

- **影響コード**: `src/dogdb/proxy/connection.py`（`execute()` の素通し分岐 137-155行、`executemany()` 242-246行、`wrap()` のシグネチャ）、`src/dogdb/core/stats.py`（理由別記録の呼び出し箇所追加）、`src/dogdb/core/errors.py`（`DollyPassthroughError` 追加）、新規の警告カテゴリ定義箇所（`DollyPassthroughWarning`）、`src/dogdb/__init__.py`（公開エクスポート）。
- **影響契約**: `openspec/specs/dbapi-proxy/spec.md`。
- **影響文書**: `README.md`（132行付近の素通し集計の記述、語彙表、`on_passthrough` の説明）、`docs/contract-v2.md`（該当があれば）。
- **non-goals**: `POLICY_VERSION` の変更（このchangeでは触らない）、sqlglot導入によるSQL分類器そのものの変更（W6-1/issue #20の射程）、素通し対象範囲自体の拡大・縮小（現行5種の分類ロジックは変更しない）、`transaction_statement`／`executemany` を発火対象へ追加するオプション。
