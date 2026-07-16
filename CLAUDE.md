# Claude Code Instructions

本プロジェクトの開発ガイドはAGENTS.mdに統合されています。

@AGENTS.md

<!-- Claude Code固有の追加指示があればここに記載 -->

The rest of this file is Claude Code–specific orchestration policy for a Fable parent agent; harness-shared policy lives in AGENTS.md, imported above.

## Model roles and delegation

Use Fable for planning, coordination, deep analysis, and insight generation. Delegate lightweight research, mechanical edits, and cleanly scoped lightweight subtasks to Sonnet. Delegate heavy research, cleanly scoped heavy subtasks, and all implementation tasks—regardless of size or complexity—to Codex configured with GPT-5.6-sol. Reserve an Opus subagent for work where a single Claude-authored voice is the point—a language-sensitive JP/EN synthesis, a delicate rewrite, a tone- or values-calibration read, or a fast inline critique on a narrow question—cases where blending several workers through a judge would dilute the voice or cost latency you can't spare.

For comparison-shaped tasks, follow the Fusion panel policy in AGENTS.md; implementation still goes to Codex. A single Opus pass is the fallback only for the narrow seat above—voice, nuance, or a latency-bound inline read—since for any other second opinion a cheap panel wins on cost, quota, and (on breadth-bound work) coverage.

In the AGENTS.md parallel-implementation (worktree) strategy, the "実装ワーカー" is Codex under this harness. When delegating into a worktree, launch the job with that worktree as its cwd — the launch cwd determines the worker's writable sandbox root as well as where its job state lives. If a wrapper subagent cannot control the launch cwd, invoke the delegation runtime directly with the worktree as cwd instead of routing through the wrapper.

## Working with subagents

Delegation is the default for breadth: sweeping, triaging, and filtering many sources is subagent work. Depth is the narrow exception: when an analysis or decision rests on a small number of primary sources, Fable reads those few directly instead of reasoning over secondhand summaries. Keep that set small and curated—Fable's own context is the scarce resource, reserved for cases where a summary's omissions would change the conclusion.

Give each subagent a clear goal, the relevant context, and what to bring back. For research tasks, have them return pointers (paths, URLs, section names) to the load-bearing sources and verbatim quotes of the decisive passages alongside their conclusions—subagent tokens are cheap, Fable's are not, so err on the side of quoting more. Don't have them invent the plan. Run independent pieces in parallel.

When they return, review the results before you merge anything. If something's off, rewrite the brief and spin another, don't silently patch over it yourself unless it's trivial.
