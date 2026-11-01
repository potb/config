---
name: workflow-blocks
description: The owner's workflow building blocks and authoring rules. Load BEFORE any Workflow tool call, before writing or editing any workflow script, and whenever the user mentions a workflow, ultracode, fan-out, multi-agent orchestration, or names a block (research, refute, design, build, gate, review, fix, land) or recipe (understand, review-fix, ship). Load it together with workflow-authoring; this skill decides what to run, workflow-authoring documents the script API.
metadata:
  trigger: Any Workflow tool call or workflow script authoring
---

# Workflow blocks

The owner keeps a library of deterministic, preconfigured workflow steps at `~/.claude/workflows/`. Use it before writing a new script. Full args, steps, default models and return shapes are in `~/.claude/workflows/README.md`; read it when you need more than the tables below.

## Order of preference

1. A recipe covers the task: run it directly.
2. A single block covers the task: run it directly.
3. Neither fits: write an ad hoc script that calls blocks through `workflow({ scriptPath })` and adds only the missing glue.
4. Only when no block fits a step at all, write that step inline, following every rule in "Rules for any workflow" below.

Before launching, state in one line which recipe or blocks you chose and why. If you wrote anything inline, say what and why no block fit.

## Calling

From the main session, pass a string or an object as args:

```
Workflow({ scriptPath: "/home/potb/.claude/workflows/recipes/understand.js", args: "the question" })
Workflow({ scriptPath: "/home/potb/.claude/workflows/blocks/review.js", args: { cwd, base, profile } })
```

Inside a script:

```
const DIR = '/home/potb/.claude/workflows/blocks/'
const research = q => workflow({ scriptPath: DIR + 'research.js' }, q)
```

A project may commit its own copy under `<repo>/.claude/workflows/`. When it exists, prefer the relative path `.claude/workflows/...` so the project's version wins; recipes already look there first.

Nesting is one level. A script you launch can call blocks. A block cannot call anything. A recipe called through `workflow()` cannot call blocks, so run recipes from the main session, never from inside another script. Calling by name does not work; always use `scriptPath`.

## Recipes

| Recipe | Use for | Chain |
|---|---|---|
| `understand` | research, technology choices, root causes, ticket analysis | research, then refute on the key claims |
| `review-fix` | a green branch before landing | review, fix, repeat until quiet (default 2 rounds) |
| `ship` | a feature that ships as one branch and one PR | design, build, gate, review and fix rounds, land; stops at owner questions, blocked units, red gate, or `stopAfter` |

## Blocks

| Block | Does | Default models |
|---|---|---|
| `research` | splits a question into lenses, gathers evidence, synthesizes | scope haiku, gather sonnet, synth opus |
| `refute` | tries to refute each claim from primary sources | skeptic sonnet |
| `design` | units with file ownership, difficulty and dependencies | designer and judge opus |
| `build` | one test-first agent per unit, worktree per unit | hard opus, easy sonnet |
| `gate` | merges unit branches, runs gates, fixes reproducible failures | integrator opus |
| `review` | lens reviewers, then one skeptic per finding | correctness opus, other lenses sonnet, skeptic sonnet |
| `fix` | one fixer, a test per finding, gates rerun | fixer opus |
| `land` | push, draft PR, watch CI, fix reproducible failures; never merges | sonnet |

Every block takes `cwd`, `profile` (path to a project profile with gates, rules, PR template and language), `context` (extra prompt text such as standing authorisations) and `models` (per-role overrides). Recipes take `models` keyed by block.

## Mapping requests to blocks

| The user asks | Run |
|---|---|
| research X, go deep, analyse, challenge my assumptions | `understand` |
| quick check of one fact or claim | `refute` with that claim, or `research` with `maxLenses: 2` |
| assess the hard parts, do spikes live | `research` for the inventory, then an ad hoc script: one live spike agent per hard part, then `refute` on each spike claim |
| plan or design X | `understand`, then `design` with its answer as `facts` |
| implement X as one PR | `ship`, usually with `stopAfter: 'design'` first so the owner can rule |
| review this branch | `review`, or `review-fix` if fixes are wanted |
| get CI green or open the PR | `gate`, then `land` |
| many tickets unattended | an ad hoc script: per ticket `build` style agents with locks and slots, `review`, `land`; keep the merge in the main session |

## Rules for any workflow, blocks or not

These come from the owner's past corrections.

- Set `model` on every `agent()` call. Never let a fleet inherit opus. Haiku for fetch, collect, close-out and mechanical work; sonnet for research, scoped implementation, refuters and verifiers; opus only for design, judging, hard implementation, integration and final synthesis.
- Use a schema on every agent whose output feeds code. Use enums for verdicts and severities.
- Put a skeptic after every finder: refute by default, unverifiable never counts as confirmed, keep a finding only on majority or reproduction.
- Bound every loop: 2 or 3 rounds, then park with one exact question for the owner. Later rounds look only at the new diff and drop minor findings.
- Flakes are rerun and reported, never counted toward stop rules. Only reproducible failures count.
- Read-only agents say so in their prompt. Agents that edit own disjoint files, or get their own worktree.
- No agent merges, force-pushes, uses `--admin`, or runs unbounded production queries. Merging stays in the main session.
- Assess before acting on large work; run the assessment as its own workflow so the owner can step in early.
- Prefer several small workflows chained by the main session, with the owner's rulings in between, over one giant script. Relaunch the same script with new args rather than writing a new one.
- Use `pipeline()` by default; use a barrier only when a stage needs every earlier result.
- `log()` every cap or dropped item.
- Never pass the owner's steering message as task input; it is guidance for you.
- Run against the right checkout: confirm the branch or worktree before analysing.
- Write reports in the session language.
- Use fd and rg, not find and grep.

## When a block falls short

If a block's behaviour is wrong for a task, pass overrides (`models`, `lenses`, `context`) first. If that is not enough, tell the owner what is missing and propose a change to the block in `~/projects/potb/config/modules/agents/claude/workflows/`, which is the source of truth; `~/.claude/workflows/` is generated from it by home-manager.
