export const meta = {
  name: 'block-research',
  description: 'Building block: split a question into lenses, gather evidence per lens, synthesize one answer',
  whenToUse: 'research("question") or research({question, lenses, cwd, profile}) before designing or deciding',
  phases: [
    { title: 'Scope', detail: 'haiku splits the question into lenses (skipped when lenses are given)' },
    { title: 'Gather', detail: 'one sonnet researcher per lens, evidence required' },
    { title: 'Synthesize', detail: 'opus merges findings into one answer' },
  ],
}

const A = typeof args === 'string' ? { question: args } : (args || {})
if (!A.question) throw new Error('research: question is required')
const M = Object.assign({ scope: 'haiku', gather: 'sonnet', synth: 'opus' }, A.models)
const CTX = [
  A.cwd && `Working directory: ${A.cwd}.`,
  A.profile && `Read the project profile at ${A.profile} first and follow its rules and language.`,
  A.context,
  'Read-only: never edit, commit or push. Use fd and rg, not find and grep.',
  'Every claim needs evidence: a URL, a file:line, or command output. Mark anything unconfirmed.',
].filter(Boolean).join('\n')

const LENSES = {
  type: 'object',
  properties: {
    lenses: {
      type: 'array',
      items: {
        type: 'object',
        properties: { name: { type: 'string' }, focus: { type: 'string' }, sources: { type: 'string' } },
        required: ['name', 'focus', 'sources'],
      },
    },
  },
  required: ['lenses'],
}
const FINDINGS = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    facts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          evidence: { type: 'string' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['claim', 'evidence', 'confidence'],
      },
    },
    openQuestions: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'facts', 'openQuestions'],
}
const SYNTH = {
  type: 'object',
  properties: {
    answer: { type: 'string' },
    keyClaims: {
      type: 'array',
      items: {
        type: 'object',
        properties: { claim: { type: 'string' }, evidence: { type: 'string' } },
        required: ['claim', 'evidence'],
      },
    },
    options: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
    openQuestions: { type: 'array', items: { type: 'string' } },
  },
  required: ['answer', 'keyClaims', 'options', 'risks', 'openQuestions'],
}

phase('Scope')
const max = A.maxLenses || 5
let lenses = A.lenses
if (!lenses) {
  const scoped = await agent(
    `${CTX}\nSplit this question into 3 to ${max} independent research lenses, each answerable on its own (for example docs, codebase, prior art, risks). Name the sources each should use.\nQUESTION: ${A.question}`,
    { label: 'scope', phase: 'Scope', schema: LENSES, model: M.scope, effort: 'low' },
  )
  lenses = scoped.lenses
}
if (lenses.length > max) log(`research: kept ${max} of ${lenses.length} lenses, dropped: ${lenses.slice(max).map(l => l.name).join(', ')}`)
lenses = lenses.slice(0, max)

const findings = (await pipeline(lenses, l => agent(
  `${CTX}\nResearch one lens of a larger question. Go deep on your lens only.\nQUESTION: ${A.question}\nLENS: ${l.name}: ${l.focus}\nSOURCES: ${l.sources || 'your choice'}`,
  { label: `gather:${l.name}`.slice(0, 40), phase: 'Gather', schema: FINDINGS, model: M.gather },
).then(f => f && Object.assign({ lens: l.name }, f)))).filter(Boolean)
if (findings.length < lenses.length) log(`research: ${lenses.length - findings.length} lens(es) returned nothing`)

phase('Synthesize')
const synthesis = await agent(
  `${CTX}\nMerge these findings into one answer. Use only the gathered facts, keep their evidence, flag contradictions between lenses, list real options with trade-offs.\nQUESTION: ${A.question}\nFINDINGS: ${JSON.stringify(findings)}`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH, model: M.synth, effort: 'high' },
)

return { question: A.question, lenses, findings, synthesis }
