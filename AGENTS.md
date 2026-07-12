## 開発フロー

- レビュー時，最低限simplifyを検討する．また，一度の実装タスクに対し，少なくとも一度はCoderabbitによるcode-reviewを実施する．
- PR時，Conversation上でレビューが実行されます．Nitpicksを含むすべての指摘に対してサブエージェント等で妥当性を確認し，必要に応じて修正を行い，指摘に対する対応についてのコメントを返す．これを，指摘がなくなるまで繰り返す．

## 並列実装（git worktree戦略）

複数の独立したchangeを一括実装する場合は、集約ブランチ（例: feature/wave-N）を切り、
changeごとにワークツリーを分離して並列実装する。

- `git worktree add ../<repo>-<略称> -b <changeブランチ> <集約ブランチ>` で分離し、
  実装は各ワークツリー内でCodexへ委譲する。プロンプト先頭を `/opsx:apply <change名>` に
  してスキルを発火させる。
- Codex sandboxはワークツリーの実Git metadata（本体側 .git/worktrees/）へ書けず
  コミットできない。コミットは親エージェントが検証（pytest / openspec validate）後に行う。
- CodeRabbit CLIもsandbox内では未認証で失敗する。レビューは親環境で
  `coderabbit review --agent -t committed --base <集約ブランチ>` を各ワークツリーで実行し、
  simplify検討と合わせてマージ前に完了させる。
- 同一ファイルを触るchange群でも並列してよいが、コンフリクト解消は集約時に親が行い、
  統合後に全テストと全changeのvalidateを再実行してからPRを立てる。
- マージ後は `git worktree remove` とブランチ削除で後片付けする。

補足2点:

1. 「codexジョブの状態はワークツリー（cwd）ごとに管理される」という運用知識も今回の発見ですが、これはcodexプラグインの実装詳細なので、AGENTS.mdに書くなら上記の箇条書きに1行足す程度、書かなくても致命傷にはなりません。入れるなら「ジョブ状態の確認は該当ワークツリー内から行う」の一文です。
2. CLAUDE.md側は変更不要です。「実装はCodexへ委譲」という既存方針の適用形にすぎず、重複記述はドリフトの温床になります。

## Fusion（ブラインドパネル審議）

When a task is comparison-shaped—critique, review, or a second opinion where independent perspectives are likely to change or sharpen the conclusion—prefer a Fusion blind panel (the bundled `skills/fusion` CLI): independent workers plus a harness-backed judge surface consensus, contradictions, partial coverage, unique insights, and blind spots, and the parent agent authors the final answer from the judge analysis, verifying load-bearing quotes with read tools. Match the panel to the stakes: cheap-model panels (e.g. gpt-5.6-sol/deepseek-v4-flash/composer-2.5 or cursor:grok-4.5 through OpenCode) cost little under current subscriptions and may be used casually for deep research, design exploration, and review-angle sweeps; reserve flagship-mixed panels for high-stakes or hard-to-reverse decisions. Work whose deliverable is a single authored voice, language-sensitive nuance, or a latency-bound read stays outside Fusion—a single strong pass serves it better than judge-stitched consensus.

Fusion is deliberation, not implementation—implementation still goes through your harness's normal implementation workflow. A panel's real costs are latency, occasional cheap-worker dropouts, and the parent agent's attention, not fees: skip Fusion for routine edits, single-source lookups, and tasks where independent reasoning would not change the outcome; partial runs are disclosed and usually still usable. While the skill is developed in parallel with real use, run panels with `--record` so live artifacts feed the compliance-evidence and judge-quality milestones.
