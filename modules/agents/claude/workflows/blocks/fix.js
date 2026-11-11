export const meta = {
  name: 'block-fix',
  description: 'Building block: one fixer applies confirmed findings with a test each, then reruns the gates',
  whenToUse: 'fix({cwd, findings, gates}) with confirmed findings from review',
  phases: [{ title: 'Fix', detail: 'single fable fixer owns the tree' }],
}

const A = args || {}
if (!A.cwd) throw new Error('fix: cwd is required')
if (!A.findings || !A.findings.length) return { fixed: [], skipped: [], gatesGreen: null, head: '' }
const M = Object.assign({ fixer: 'fable' }, A.models)
const CTX = [
  `Repository: ${A.cwd}. You are the only agent touching this tree.`,
  A.profile && `Read the project profile at ${A.profile} first.`,
  A.context,
  A.gates && A.gates.length ? `Gates: ${A.gates.join(' && ')}` : 'Use the gates from the profile or repo scripts.',
  'Use fd and rg. Never push, never merge. Report only checks you actually ran.',
].filter(Boolean).join('\n')

const RESULT = {
  type: 'object',
  properties: {
    fixed: { type: 'array', items: { type: 'string' }, description: 'finding title and the test that covers it' },
    skipped: {
      type: 'array',
      items: { type: 'object', properties: { title: { type: 'string' }, reason: { type: 'string' } }, required: ['title', 'reason'] },
    },
    gatesGreen: { type: 'boolean' },
    head: { type: 'string' },
  },
  required: ['fixed', 'skipped', 'gatesGreen', 'head'],
}

phase('Fix')
const r = await agent(
  `${CTX}\nFor each finding: re-check it is real, add a test that fails, fix it minimally, see the test pass. Skip with a reason if not real. Then run every gate and commit.\nFINDINGS: ${JSON.stringify(A.findings)}`,
  { label: 'fix', phase: 'Fix', schema: RESULT, model: M.fixer },
)
return r || { fixed: [], skipped: [], gatesGreen: false, head: '' }
