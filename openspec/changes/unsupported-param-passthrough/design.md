# unsupported-param-passthrough — Design

## Context

`DecisionEngine.begin()`（decision.py:33-37）は `include_params` の設定に関わらず全ての通常 execute で `parameter_fingerprint()` を呼び、`_json_default`（fingerprints.py:30-41）がホワイトリスト外の型に `TypeError` を送出する。この挙動は determinism 契約の明示的 MUST（不安定エンコードのイベント混入防止が根拠）だが、次の実測により問題が確定している：

- sqlite3 の `__conform__` プロトコル実装型は**生接続では正常に実行される**が、全障害確率0のラッパーでは実行前に `TypeError` でクラッシュする。
- 一方、名前付きパラメータ（Mapping）は `execute()` 冒頭（connection.py:135-142）で「静かな素通し」となりクエリは実行される。同じ「fingerprint を安定に作れない」状況への対応が非対称。

Fusion パネル（3ワーカー）は 2対1 で素通し合流を推奨し、フォールバック fingerprint は全員一致で棄却。破壊許可レンズ（リリース前）の適用で素通し合流に決着した（grilling 確定）。

## Goals / Non-Goals

**Goals:**
- 確率0のラッパーが、生接続なら成功する操作を失敗させないこと（非介入性の回復）。
- 決定性保証を弱めないこと: 不安定な値をイベント系列・決定キーに一切参加させない。
- 素通しの発生を観測可能にすること。

**Non-Goals:**
- フォールバック fingerprint（repr／pickle／型名）。`include_params=True` の「パラメータが運命を分ける」意味論を型名 fingerprint は満たせず、repr 系は再現性を破る。
- 名前付きパラメータ・executemany・分類不能文の既存素通し挙動の変更。
- 入力域自体の拡張（新しい型の fingerprint 対応は将来の別 change）。

## Decisions

### D1: 検出は「実行前の型判定」で行い、try/except に依存しない
`begin()` 呼び出し前に、パラメータ列を許可リストで走査する純粋関数（例: `params_in_fingerprint_domain(params) -> bool`）を設ける。**代替案**: `parameter_fingerprint` を try/except TypeError で包む — 例外経路が「JSON化の他の失敗」と混線し、判定の決定性が実装詳細（json.dumps の内部挙動）に依存するため不採用。判定関数は許可リスト（determinism 契約の閉じた列挙）のみに依存する純粋関数とし、判定自体が決定的であることを保証する。

### D2: 素通し分岐の位置は既存の早期 return と同じ場所
`execute()` の既存分岐（Mapping / UNKNOWN / transaction → adapter 直行）に入力域判定を追加する。`_begin_operation()` の**後**に置き、論理時計が進む現行の素通し挙動と揃える（パネルで対立した論点。「現行の named/UNKNOWN は時計を進めている」という実装事実に基づき一貫性側で決着）。

### D3: occurrence は消費しない
素通し操作は `begin()` を呼ばないため occurrence カウンタに触れない。これは「素通し操作を挟んでも後続クエリの decision_key が不変」という回帰保証になる（spec のシナリオとして固定）。将来この操作を注入対象に昇格させる場合は replay 系列が変わるため、POLICY_VERSION 判断が必要になることを契約注記に残す（Fusion パネル gpt-5.6-sol の先回り指摘）。

### D4: stats カウンタは名前バケットのみ
`StatsTracker` に `passthrough` 集計を追加し、`unsupported_parameter_type` キーで計数する。型名・値・repr は記録しない（機密原則＋「型名すら不安定になりうる」ため）。W1-a の `escape_hatches` とはキー空間を分ける（属性転送と操作素通しは別概念）。

### ADR: 破壊的変更の宣言

- **何が壊れるか**: determinism 契約の「入力域外は実行前に `TypeError` で拒否（MUST）」要件と、それを固定していたテスト。API 利用者視点では「落ちていた操作が実行されるようになる」方向の変更であり、実行結果の互換性は生接続側に揃う。
- **なぜ設計的に妥当か**: 旧 MUST の目的（不安定エンコードをイベント系列に混入させない）は、イベント自体を生成しない素通しでも完全に達成される。つまり目的を保ったまま、テスト用ラッパーが被テストアプリより先に落ちるという副作用だけを除去できる。名前付きパラメータとの非対称も解消される。
- **移行方法**: `TypeError` を期待していたテストは素通し検証（結果同一性＋イベント不生成＋カウンタ増分）に書き換える。利用者コードの移行作業は不要（挙動は寛容側に変わる）。

## Risks / Trade-offs

- [素通しの静かな拡大がバイパス面を広げる] → W1-a（fail-closed）と本 change の stats カウンタが観測性を担保する。両 change は同 Wave で実施される。
- [判定関数と `parameter_fingerprint` 本体の入力域がズレる] → 単一の許可リスト定数を両者で共有し、プロパティテスト（判定 True の値は必ず fingerprint 可能）で固定する。
- [混在パラメータ列（一部だけ入力域外）の扱い] → 1つでも入力域外なら操作全体を素通し（部分 fingerprint は「同一入力列は同一イベント列」を破るため不可）。
- [W3-b（fast path）との整合] → 本 change が「fingerprint はいつ必要か」を確定させるため、W3-b は本 change の完了を前提とする（依存関係は統括 #11 に記載済み）。

## Migration Plan

1. 入力域判定の純粋関数を追加（非破壊）。
2. `execute()` に素通し分岐を追加し、stats カウンタを接続（挙動変更点）。
3. determinism spec の旧シナリオ（TypeError 拒否）を固定していたテストを素通し検証へ書き換え。
4. ロールバックは分岐の除去のみで完結する。

## Open Questions

（なし——grilling で全論点決着済み）
