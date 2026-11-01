export const meta = {
  name: 'block-refute',
  description: 'Building block: try to refute each claim from primary sources, refuted by default when uncertain',
  whenToUse: 'refute({claims, cwd}) after research or review, to keep only claims that survive',
  phases: [{ title: 'Refute', detail: 'N sonnet skeptics per claim, majority decides' }],
}

const A = Array.isArray(args) ? { claims: args } : (args || {})
if (!A.claims || !A.claims.length) return { verdicts: [], confirmed: [], refuted: [], unverifiable: [] }
const M = Object.assign({ skeptic: 'sonnet' }, A.models)
const VOTES = A.votes || 1
const CTX = [
  A.cwd && `Working directory: ${A.cwd}.`,
  A.profile && `Read the project profile at ${A.profile} first.`,
  A.context,
  'Read-only: never edit, commit or push. Use fd and rg. You may run read-only commands and scratch tests outside the repo.',
].filter(Boolean).join('\n')

const VERDICT = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['confirmed', 'refuted', 'unverifiable'] },
    evidence: { type: 'string', description: 'file:line, URL or command output that decided it' },
    correction: { type: 'string', description: 'the true statement when refuted, else empty' },
  },
  required: ['status', 'evidence', 'correction'],
}

const decide = votes => {
  const confirmed = votes.filter(v => v.status === 'confirmed').length
  const refuted = votes.filter(v => v.status === 'refuted').length
  if (confirmed * 2 > VOTES) return 'confirmed'
  if (refuted > 0 && refuted >= confirmed) return 'refuted'
  return 'unverifiable'
}

const claims = A.claims.map(c => (typeof c === 'string' ? { claim: c, evidence: '' } : c))
const verdicts = await pipeline(claims, (c, _, i) => parallel(Array.from({ length: VOTES }, (_v, k) => () => agent(
  `${CTX}\nTry hard to REFUTE this claim using primary sources (code, node_modules, official docs, live read-only commands). Do not trust the stated evidence; check it. If you cannot confirm it from a primary source, answer unverifiable. Unverifiable never counts as confirmed.\nCLAIM: ${c.claim}\nSTATED EVIDENCE: ${c.evidence || 'none'}`,
  { label: `refute:${i}${VOTES > 1 ? '.' + k : ''}`, phase: 'Refute', schema: VERDICT, model: M.skeptic },
))).then(vs => {
  const ok = vs.filter(Boolean)
  const status = decide(ok)
  const decider = ok.find(v => v.status === status) || ok[0] || { evidence: 'no verdict returned', correction: '' }
  return Object.assign({}, c, { status, evidence: decider.evidence, correction: decider.correction, votes: ok.map(v => v.status) })
}))

const done = verdicts.filter(Boolean)
return {
  verdicts: done,
  confirmed: done.filter(v => v.status === 'confirmed'),
  refuted: done.filter(v => v.status === 'refuted'),
  unverifiable: done.filter(v => v.status === 'unverifiable'),
}
