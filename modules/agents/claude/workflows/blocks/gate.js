export const meta = {
  name: 'block-gate',
  description: 'Building block: merge built branches, run every gate, fix until green within a round budget',
  whenToUse: 'gate({cwd, gates, branches}) after build, or alone to get a tree green',
  phases: [{ title: 'Gate', detail: 'one opus integrator owns the tree, flakes rerun and never counted' }],
}

const A = args || {}
if (!A.cwd) throw new Error('gate: cwd is required')
const M = Object.assign({ integrator: 'opus' }, A.models)
const ROUNDS = A.maxRounds || 3
const CTX = [
  `Repository: ${A.cwd}. You are the only agent touching this tree.`,
  A.profile && `Read the project profile at ${A.profile} first; it lists the gates in CI order.`,
  A.context,
  A.gates && A.gates.length ? `Gates in order: ${A.gates.join(' && ')}` : 'Use the gates from the profile or the repo scripts, in CI order.',
  A.e2e && `E2E command (you are the only runner): ${A.e2e}`,
  'A failure counts only if it reproduces on rerun; flakes are reported, never counted.',
  'Use fd and rg. Never push, never merge to a remote branch.',
].filter(Boolean).join('\n')

const STATE = {
  type: 'object',
  properties: {
    green: { type: 'boolean' },
    failures: { type: 'array', items: { type: 'string' }, description: 'reproducible failures left' },
    flaky: { type: 'array', items: { type: 'string' } },
    fixes: { type: 'array', items: { type: 'string' } },
    head: { type: 'string', description: 'commit sha of the tree' },
  },
  required: ['green', 'failures', 'flaky', 'fixes', 'head'],
}

phase('Gate')
const history = []
for (let round = 1; round <= ROUNDS; round++) {
  const mergeFirst = round === 1 && A.branches && A.branches.length
  const prev = history[history.length - 1]
  const s = await agent(
    `${CTX}\n${mergeFirst ? `First merge these branches into the current branch, resolving conflicts by intent: ${A.branches.join(', ')}.\n` : ''}Run every gate. Fix reproducible failures with the smallest correct change and commit. Round ${round} of ${ROUNDS}.${prev ? '\nPREVIOUS ROUND: ' + JSON.stringify(prev) : ''}`,
    { label: `gate:r${round}`, phase: 'Gate', schema: STATE, model: M.integrator },
  )
  if (!s) break
  history.push(s)
  if (s.green) break
}
const last = history[history.length - 1] || { green: false, failures: ['no gate result'], flaky: [], fixes: [], head: '' }
if (!last.green) log(`gate: still red after ${history.length} round(s): ${last.failures.join('; ')}`)
return Object.assign({ rounds: history.length, history }, last)
