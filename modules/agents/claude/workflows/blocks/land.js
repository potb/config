export const meta = {
  name: 'block-land',
  description: 'Building block: push, open a draft PR from the repo template, watch CI, fix reproducible failures, stop at ready',
  whenToUse: 'land({cwd, base}) once the branch is green and reviewed; never merges',
  phases: [
    { title: 'PR', detail: 'sonnet pushes and opens a draft PR' },
    { title: 'CI', detail: 'sonnet watches checks and fixes only reproducible failures' },
  ],
}

const A = args || {}
if (!A.cwd || !A.base) throw new Error('land: cwd and base are required')
const M = Object.assign({ pr: 'sonnet', ci: 'sonnet' }, A.models)
const CTX = [
  `Repository: ${A.cwd}. Target base branch: ${A.base}.`,
  A.profile && `Read the project profile at ${A.profile} first; follow its PR template and language.`,
  A.context,
  'Never merge, never force-push to a shared branch, never use --admin. Use gh for GitHub.',
].filter(Boolean).join('\n')

const PR = {
  type: 'object',
  properties: { number: { type: 'integer' }, url: { type: 'string' }, head: { type: 'string' } },
  required: ['number', 'url', 'head'],
}
const CI = {
  type: 'object',
  properties: {
    green: { type: 'boolean' },
    ready: { type: 'boolean' },
    failures: { type: 'array', items: { type: 'string' } },
    flaky: { type: 'array', items: { type: 'string' } },
    mergeState: { type: 'string' },
  },
  required: ['green', 'ready', 'failures', 'flaky', 'mergeState'],
}

phase('PR')
const pr = await agent(
  `${CTX}\nRebase on ${A.base} if behind, push the branch, open a DRAFT PR against ${A.base}${A.title ? ' titled "' + A.title + '"' : ''} with a body from the repo template: what changed, why, how it was tested${A.screenshots ? ', screenshots of every UI state' : ''}. Return the PR number, URL and head sha.`,
  { label: 'pr', phase: 'PR', schema: PR, model: M.pr },
)
if (!pr) return { pr: null, ci: null }

phase('CI')
const ci = await agent(
  `${CTX}\nWatch checks on PR #${pr.number} with gh pr checks --watch. For a failure, reproduce it locally; fix and push only if it reproduces, at most ${A.maxCiFixes || 2} times; rerun once if it does not. ${A.ready ? 'When all required checks are green, mark the PR ready with gh pr ready.' : 'Leave the PR as draft.'} Do not return before required checks finish.`,
  { label: 'ci', phase: 'CI', schema: CI, model: M.ci },
)
return { pr, ci }
