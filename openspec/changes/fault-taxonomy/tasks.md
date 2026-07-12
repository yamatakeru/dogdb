# tasks — fault-taxonomy

## 1. taxonomyの一次定義（core）

- [x] 1.1 `core/faults.py` に fault（モード分岐含む）→（category, severity, rowcount可視）の不変対応表を定義する（design D3/D8 の表と一致させる）
- [x] 1.2 対応表と `KNOWN_FAULTS` の一対一（全 fault がちょうど1回、モード分岐 fault は全モード）を検証するテストを追加する（design D4）

## 2. 例外への公開

- [x] 2.1 `core/errors.py` の `DogDBError` に読み取り専用プロパティ `category` / `severity` を追加する（design D5。既存属性は現状維持、`DollyTailChaseError` の追加kwargとの整合を確認）
- [x] 2.2 例外送出経路（`_raise_before_execute`・NO_DROP・STASH error・TAIL_CHASE error・DollyLimitError）で値を渡す。`DollyLimitError` は None / None（design D5）

## 3. イベントへの公開

- [x] 3.1 `core/event_log.py` の `Event` に任意フィールド `category` / `severity` を宣言し、`_STRING_FIELDS` へ追加する（`_V2_FIELDS` の必須集合には追加しない、design D6）
- [x] 3.2 `core/faults.py` の `fault_injected` 記録経路（`_event` 呼び出し）で値を渡す。`treasure_returned`・`decision_evaluated`・`limit_exceeded`・`mood_changed` には付与しない（design D6）

## 4. 暫定集合の解消（proxy）

- [x] 4.1 `proxy/connection.py` の `_ROWCOUNT_VISIBLE_FAULTS` を taxonomy の rowcount 可視フラグ参照へ置換し、「provisional」コメントを解消する（design D8）
- [x] 4.2 置換前後で集合が現行の5 fault（FALSE_EMPTY・TAIL_CHASE・ECHO・PAGE_HOLE・WRONG_COUNT）と同値であることをテストで固定する

## 5. テストと検証

- [x] 5.1 例外属性のテストを追加する: BARK 発火例外の category/severity、読み取り専用（代入で `AttributeError`）、上限超過例外は None/None
- [x] 5.2 イベントフィールドのテストを追加する: CHEW/SHUFFLE の fault_injected に分類が載る、STASH のモード分岐（missing/error で severity が分かれる）、treasure_returned には載らない
- [x] 5.3 replay 互換のテストを追加する: 分類フィールドなしの既存 v2 ログとの replay 比較が成功する
- [x] 5.4 `pytest` 全体を実行し、既存テスト（v3 golden 回帰・イベント期待値を含む）が無変更で通ることを確認する（decision key 不参加・必須フィールド不変の検証を兼ねる）

## 6. 文書とチェック

- [x] 6.1 `docs/contract-v2.md` を更新する: fault 合成規則表の classification 列を category / severity の2列へ更新（評価順は不変）、イベント任意フィールドの記載、決定タグ表に category / severity を追加しないことの明記、新障害の命名基準（「犬の行動 × 1語で結果形状が想像できる」＋対応表への同時登録）の文書化
- [x] 6.2 `README.md` に分類属性によるテストフィルタの例を追記する（該当節がある場合）
- [x] 6.3 `openspec validate fault-taxonomy` と pyright ベースライン（src/dogdb 6 errors 維持）を確認する

## 7. 完了処理（マージ後）

- [ ] 7.1 issue #10 へ完了コメントを投稿する（`Closes #10` により自動クローズ）
- [ ] 7.2 統括 issue #11 の W4-b チェックボックスを更新する
