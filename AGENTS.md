## 開発フロー

- レビュー時，最低限simplifyを検討する．また，一度の実装タスクに対し，少なくとも一度はCoderabbitによるcode-reviewを実施する．

## Fusion（ブラインドパネル審議）

When a task is comparison-shaped—critique, review, or a second opinion where independent perspectives are likely to change or sharpen the conclusion—prefer a Fusion blind panel (the bundled `skills/fusion` CLI): independent workers plus a harness-backed judge surface consensus, contradictions, partial coverage, unique insights, and blind spots, and the parent agent authors the final answer from the judge analysis, verifying load-bearing quotes with read tools. Match the panel to the stakes: cheap-model panels (e.g. gpt-5.6-sol/deepseek-v4-flash/composer-2.5 or cursor:grok-4.5 through OpenCode) cost little under current subscriptions and may be used casually for deep research, design exploration, and review-angle sweeps; reserve flagship-mixed panels for high-stakes or hard-to-reverse decisions. Work whose deliverable is a single authored voice, language-sensitive nuance, or a latency-bound read stays outside Fusion—a single strong pass serves it better than judge-stitched consensus.

Fusion is deliberation, not implementation—implementation still goes through your harness's normal implementation workflow. A panel's real costs are latency, occasional cheap-worker dropouts, and the parent agent's attention, not fees: skip Fusion for routine edits, single-source lookups, and tasks where independent reasoning would not change the outcome; partial runs are disclosed and usually still usable. While the skill is developed in parallel with real use, run panels with `--record` so live artifacts feed the compliance-evidence and judge-quality milestones.
