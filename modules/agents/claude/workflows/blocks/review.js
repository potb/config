export const meta = {
  name: 'block-review',
  description: 'Building block: multi-lens read-only review, each finding checked by a skeptic that defaults to not real',
  whenToUse: 'review({cwd, base}) on a branch; returns confirmed findings only',
  phases: [
    { title: 'Review', detail: 'one reviewer per lens (fable for correctness, sonnet otherwise)' },
    { title: 'Verify', detail: 'one sonnet skeptic per finding, chained behind its lens' },
  ],
}

const A = args || {}
if (!A.cwd) throw new Error('review: cwd is required')
const M = Object.assign({ skeptic: 'sonnet', lens: 'sonnet', correctness: 'fable' }, A.models)
const LENSES = A.lenses || [
  { name: 'correctness', focus: 'logic bugs, edge cases, races, error handling, data loss' },
  { name: 'rules-tests-docs', focus: 'repo rules, test quality and coverage, docs drift against code' },
  { name: 'security', focus: 'authz, injection, secrets, unsafe prod access' },
]
const lensModel = l => l.model || M[l.name] || M.lens
const RANK = { minor: 0, major: 1, blocker: 2 }
const MIN = RANK[A.minSeverity || 'minor']
const CAP = A.maxPerLens || 12
const VERIFY = A.verify !== false
const CTX = [
  `Repository: ${A.cwd}. Review the diff of the current branch against ${A.base || 'its merge base with the default branch'}.`,
  A.profile && `Read the project profile at ${A.profile} first; its rules are part of the review.`,
  A.focus && `Focus: ${A.focus}`,
  A.context,
  'Read-only: never edit, commit or push. Use fd and rg.',
].filter(Boolean).join('\n')

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['minor', 'major', 'blocker'] },
          failure: { type: 'string', description: 'concrete input or state that breaks' },
          fix: { type: 'string' },
        },
        required: ['title', 'file', 'line', 'severity', 'failure', 'fix'],
      },
    },
  },
  required: ['findings'],
}
const VERDICT = {
  type: 'object',
  properties: { real: { type: 'boolean' }, evidence: { type: 'string' } },
  required: ['real', 'evidence'],
}

const perLens = await pipeline(
  LENSES,
  l => agent(`${CTX}\nReview through one lens only: ${l.name}: ${l.focus}. Report at most ${CAP} findings, most severe first. Drop anything you cannot point to in code.`, {
    label: `review:${l.name}`.slice(0, 40), phase: 'Review', schema: FINDINGS, model: lensModel(l),
  }),
  (r, l) => {
    const kept = ((r && r.findings) || []).filter(f => RANK[f.severity] >= MIN).map(f => Object.assign({ lens: l.name }, f))
    if (!VERIFY) return kept.map(f => Object.assign({ verified: false, real: true }, f))
    return parallel(kept.map((f, i) => () => agent(
      `${CTX}\nTry to prove this review finding is NOT real: read the code, run a scratch test outside the repo if useful. Default to real=false when the evidence is weak.\nFINDING: ${JSON.stringify(f)}`,
      { label: `verify:${l.name}:${i}`.slice(0, 40), phase: 'Verify', schema: VERDICT, model: M.skeptic },
    ).then(v => Object.assign({}, f, { verified: true, real: !!(v && v.real), verifyEvidence: v ? v.evidence : 'no verdict' }))))
  },
)

const all = perLens.filter(Boolean).flat().filter(Boolean)
const confirmed = all.filter(f => f.real).sort((a, b) => RANK[b.severity] - RANK[a.severity])
log(`review: ${all.length} raw finding(s), ${confirmed.length} kept`)
return { confirmed, rejected: all.filter(f => !f.real), lenses: LENSES.map(l => l.name) }
