# Workflow building blocks

Deterministic, preconfigured workflow steps. Each block is one standalone Workflow script with fixed phases, fixed
models per role, structured output and its safety rules built in. Recipes chain blocks with `workflow({scriptPath})`.

Workflow scripts cannot `import`, `require` or `eval`, and saved workflows are not resolved by name from this folder,
so blocks are always called by absolute path.

## Calling

From the main session:

```
Workflow({ scriptPath: "/home/potb/.claude/workflows/blocks/research.js", args: "my question" })
Workflow({ scriptPath: "/home/potb/.claude/workflows/recipes/ship.js", args: { goal, cwd, base, gates, profile } })
```

From inside a recipe or any ad hoc script:

```
const DIR = '/home/potb/.claude/workflows/blocks/'
const research = q => workflow({ scriptPath: DIR + 'research.js' }, q)
const r = await research('can we move X to Y')
```

Nesting is one level: a recipe can call blocks, a block cannot call anything, and a recipe called through
`workflow()` cannot call blocks. Run recipes from the main session.

## Shared args

Every block accepts these, all optional:

| Arg | Meaning |
|---|---|
| `cwd` | repository or working directory |
| `profile` | path to a project profile markdown file (gates in CI order, rules, PR template, language); agents read it first |
| `context` | extra text prepended to every agent prompt (standing authorisations, safety rules) |
| `models` | override the model per role, for example `{ gather: 'haiku' }` |

Recipes look for blocks in `.claude/workflows/blocks/` relative to the session's working directory first (a project
copy committed to the repo), then fall back to `/home/potb/.claude/workflows/blocks/`. `blocksDir` forces one folder.

Recipes take `models` keyed by block, for example `{ research: { synth: 'sonnet' }, review: { skeptic: 'haiku' } }`,
and `blocksDir` to point at another copy of the blocks.

## Blocks

| Block | Args | Steps and default models | Returns |
|---|---|---|---|
| `research` | string, or `{ question, lenses?, maxLenses? }` | scope (haiku, skipped when lenses given), gather per lens (sonnet), synthesize (opus) | `{ question, lenses, findings, synthesis: { answer, keyClaims, options, risks, openQuestions } }` |
| `refute` | array of claims, or `{ claims, votes? }` | per claim, `votes` skeptics (sonnet), refuted or unverifiable unless a majority confirms | `{ verdicts, confirmed, refuted, unverifiable }` |
| `design` | string, or `{ goal, facts?, angles? }` | one designer (opus), or one per angle plus a judge (opus) | `{ goal, design: { summary, units, decisions, risks, ownerQuestions } }` |
| `build` | `{ units, base?, gates?, worktree? }` | one agent per unit following `dependsOn`; opus when `hard`, sonnet otherwise; worktree per unit unless `worktree: false` | `{ results, branches, blocked }` |
| `gate` | `{ gates?, branches?, e2e?, maxRounds? }` | one integrator (opus) merges branches, runs gates, fixes reproducible failures, up to 3 rounds | `{ green, failures, flaky, fixes, head, rounds, history }` |
| `review` | `{ base?, lenses?, focus?, minSeverity?, maxPerLens?, verify? }` | per lens reviewer (correctness opus, rules-tests-docs and security sonnet), then one skeptic per finding (sonnet). Lens model resolves as `lens.model`, then `models[lensName]`, then `models.lens` | `{ confirmed, rejected, lenses }` |
| `fix` | `{ findings, gates? }` | one fixer (opus), a test per fix, gates rerun | `{ fixed, skipped, gatesGreen, head }` |
| `land` | `{ base, title?, ready?, screenshots?, maxCiFixes? }` | push and draft PR (sonnet), watch CI and fix reproducible failures (sonnet); never merges | `{ pr, ci }` |

A unit for `build` is `{ id, title, brief, owns: [paths], hard: boolean, dependsOn: [ids] }`, the same shape `design`
returns.

## Recipes

| Recipe | Chain | Stops early when |
|---|---|---|
| `understand` | research, then refute on the key claims | never |
| `review-fix` | review, fix, repeat up to `maxRounds` (default 2); later rounds look at the fix diff and majors only | review is quiet |
| `ship` | design (skipped with `units`), build, gate, review and fix rounds, land | design has owner questions, units are blocked, gate stays red, or `stopAfter` is reached; `autonomous: true` skips the first two stops |

`ship` takes `stopAfter: 'design' | 'build' | 'gate' | 'review' | 'land'` so each phase can run as its own call with a
ruling in between.

## Rules baked into every block

- Explicit model on every agent; nothing inherits the session model.
- Read-only blocks (`research`, `refute`, `design`, `review`) never edit, commit or push.
- No block merges. `land` stops at a draft or ready PR; merging stays in the main session.
- Flakes are rerun and reported, never counted as failures.
- Checks are reported only if they were actually run.
- fd and rg instead of find and grep.
- Caps and dropped items are logged, never silent.
