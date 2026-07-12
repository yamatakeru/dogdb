## Context

現在の実行パイプラインは、ゼロ確率設定でも操作ごとに次の暗号学的計算を行う:

- `proxy/connection.py execute()`: `template_fingerprint(sql)`（統計用、connection.py:137）→ `DecisionEngine.begin()` 内で**同じfingerprintを再計算**（decision.py:34）＋ `parameter_fingerprint`（HMAC、無条件）→ `decide()` ×2 phase（SHA-256各1回、scopedでなくても計算）。
- `faults.py _fires()`: 確率を取得した**後**、確率が0でも発火判定ハッシュを導出してから `probability > 0` を評価する（faults.py:178-194）。

実測: ゼロ確率の小SELECT 2000回で素15ms→ラップ455ms（約30倍）。

前提となる制約:

- `FaultPolicy` は実行時可変。`stash` / `shuffle` / `ignore` のプロパティsetterが公開され、テストが実際にセッション途中で重みを変更する（tests/test_conformance.py の `conn._faults.policy.ignore = 0`）。
- mood有効時の実効重みは base × mood係数 でtickごとに変わる（faults.py:181-182）。
- `debug=True` は発火しない決定にも `decision_evaluated` イベントを記録し、decision key と parameter fingerprint を消費する（faults.py:406-424）。
- `stale_cache`（OLD_BONE > 0 のwrap時のみ生成）はSELECTごとに on_result decision を保存する（connection.py:172-177）。
- `decide()` は副作用のない純関数（decision.py:39-58）。`begin()` はoccurrenceカウンタを進める副作用を持つ（decision.py:33-37）。

## Goals / Non-Goals

**Goals:**

- ゼロ実効重みの操作から、観測可能な出力に寄与しない暗号学的導出を排除する（合格ゲート: 素の5倍以内）。
- あらゆる設定でW3-a基準線とbyte-for-byte一致（decision key / fault / occurrence / イベント / 論理結果 / stats）を保つ。

**Non-Goals:**

- classify_sql・統計記録・論理時計・occurrence管理の省略。
- mood導出の最適化。素通し判定の変更。決定値のいかなる変更。

## Decisions

### D1: 実効重みの判定は操作ごと・phaseごとに評価し、wrap時にキャッシュしない

`FaultPolicy` の実行時可変性とmood係数のtick依存性のため、「このセッションはゼロ確率」という静的な事前判定は誤りになる。fast pathの入口判定は毎操作、phase候補集合に対して `policy.probability(f) × mood係数 > 0` を評価する。この判定自体は辞書参照と乗算のみでハッシュを含まない。

### D2: `_fires` は確率を先に評価し、確率0なら導出しない

`return probability > 0 and (probability >= 1 or value < probability)` の `value` 導出を確率チェックの後ろへ移す。導出値は `probability <= 0` のとき現状でも未使用なので、挙動は同一。これは per-fault の除外であり、混在設定（一部の障害だけ非0）でも効く。

### D3: 観測不能なら `decide()` 自体をスキップする

decision key が観測可能な出力へ到達する経路は (a) 発火イベント・宝物、(b) debugの `decision_evaluated` イベント、(c) stale cacheエントリ、の3つに閉じる。したがって:

- before_execute の decide は `scoped かつ (debug または before phase候補に実効重み>0がある)` のときだけ計算する。
- on_result の decide は `scoped かつ ((not before_consumed かつ (debug または on_result候補に実効重み>0)) または (stale_cacheあり かつ SELECT))` のときだけ計算する。

`decide()` は純関数でありスキップは後続操作の決定に影響しない（occurrenceは `begin()` が進め続ける）。スキップした操作の後に重みが非0へ変わっても、次操作の decision key は従来と同一の純関数値になる。

### D4: `template_fingerprint` は execute() で1回計算し `begin()` へ渡す

統計記録（素通し操作を含む全操作で必要）はexecute冒頭の計算を維持し、`begin()` が省略可能引数で受け取って再計算を省く。fingerprintの値・意味は不変。

### D5: `parameter_fingerprint` はメモ化サプライヤで遅延評価する

`begin()` は即値の代わりに1操作スコープのメモ化サプライヤ（初回呼び出しでHMACを計算し以後キャッシュ）を提供し、次の消費点で初めて解決する: (a) `include_params=True` の `decide()` 入力、(b) イベント・宝物・staleエントリの生成、(c) debugイベント。解決値は現行と同一のため、計算の有無以外に観測差はない。表現（thunk / lazyフィールド / Decisionの遅延プロパティ）は実装に委ねるが、1操作で最大1回しか計算しないこと。

### D6: ベンチマークは再現可能なスクリプトとして常置し、CIの断言にはしない

`benchmarks/zero_weight_overhead.py` を新設: `:memory:` SQLiteで小SELECT×2000を素/ラップ（全重み0）で複数回測り、中央値の比を報告する。壁時計に依存する閾値テストはCIでフレークするため、5倍ゲートはPR時にスクリプトの実測値を記録して判定する。

### D7: classify_sql・統計・論理時計はfast pathでも維持する

統括issueのパネル審議（2/3採用)で決定済み。切るとUNKNOWN率・corpus計測（`dolly.stats()`）が失われ、「全確率0で導入して観測する」導線自体が壊れる。`_begin_operation()`（論理時計・mood・自動返却）も無条件に実行し続ける。

## Risks / Trade-offs

- [遅延fingerprintの解決漏れ] イベント生成経路で未解決のままシリアライズされると事故になる → 全障害の発火系テスト（conformance / shape / value / availability）とW3-aゴールデン回帰テストが無変更で通ることを合格ゲートとし、解決漏れは即検出される。
- [decide()スキップ述語の誤り] debug・stale cache・before_consumed の見落としはイベント欠落として現れる → fast path固有テスト（debug=True で `decision_evaluated` が従来どおり出る、OLD_BONE有効時のstale参照不変、重み0→非0の実行時変更でdecision key不変）を追加する。
- [mood係数の参照が状態を進める誤実装] `mood.multiplier()` は読み取り専用であること（advanceは `_begin_operation` のみ）を前提とする。実効重み判定でこれを崩さない。
- [5倍ゲートの環境依存] 測定条件（バックエンド・クエリ・反復数・中央値）をスクリプトに固定し、比（絶対時間でなく）で判定して環境差を吸収する。

## Migration Plan

1. `faults.py _fires`: 確率チェックを導出の前へ（D2）。
2. `decision.py begin`: template fingerprint受け渡し（D4）とparameter fingerprintの遅延化（D5）。
3. `proxy/connection.py execute`: phase別のdecide()スキップ述語（D3）。
4. fast path固有テストを追加し、既存全テスト＋W3-aゴールデンが無変更で通ることを確認。
5. `benchmarks/zero_weight_overhead.py` を追加し実測、PRに記録。
6. 非破壊のため契約文書の変更なし。ロールバックは単一PRのrevert。

## Open Questions

（なし——W3-a完了後に `/opsx:update` で基準線との整合を再確認してから着手する）
