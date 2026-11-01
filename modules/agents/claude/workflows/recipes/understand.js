export const meta = {
  name: 'recipe-understand',
  description: 'Recipe: research a question, then refute every key claim before trusting the answer',
  whenToUse: 'understand("question") or understand({question, cwd, profile, votes}) for any research or decision',
  phases: [
    { title: 'Research', detail: 'block-research' },
    { title: 'Refute', detail: 'block-refute on the key claims' },
  ],
}

const A = typeof args === 'string' ? { question: args } : (args || {})
const DIRS = A.blocksDir ? [A.blocksDir] : ['.claude/workflows/blocks/', '/home/potb/.claude/workflows/blocks/']
const models = A.models || {}
const call = async (block, input) => {
  const payload = Object.assign({ models: models[block] }, input)
  for (const dir of DIRS) {
    try {
      return await workflow({ scriptPath: dir + block + '.js' }, payload)
    } catch (e) {
      if (!/Workflow script file not found/.test(e.message) || dir === DIRS[DIRS.length - 1]) throw e
    }
  }
}
const shared = { cwd: A.cwd, profile: A.profile, context: A.context }

phase('Research')
const research = await call('research', Object.assign({}, shared, { question: A.question, lenses: A.lenses, maxLenses: A.maxLenses }))

phase('Refute')
const verdicts = await call('refute', Object.assign({}, shared, { claims: research.synthesis.keyClaims, votes: A.votes || 1 }))
log(`understand: ${verdicts.confirmed.length} confirmed, ${verdicts.refuted.length} refuted, ${verdicts.unverifiable.length} unverifiable`)

return {
  question: A.question,
  answer: research.synthesis.answer,
  options: research.synthesis.options,
  risks: research.synthesis.risks,
  openQuestions: research.synthesis.openQuestions,
  confirmed: verdicts.confirmed,
  refuted: verdicts.refuted,
  unverifiable: verdicts.unverifiable,
  findings: research.findings,
}
