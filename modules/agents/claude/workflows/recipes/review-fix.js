export const meta = {
  name: 'recipe-review-fix',
  description: 'Recipe: review with skeptics, fix confirmed findings, repeat until quiet or out of rounds',
  whenToUse: 'reviewFix({cwd, base, gates}) on a green branch before landing',
  phases: [
    { title: 'Review', detail: 'block-review each round' },
    { title: 'Fix', detail: 'block-fix when anything is confirmed' },
  ],
}

const A = args || {}
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
const ROUNDS = A.maxRounds || 2

const rounds = []
for (let round = 1; round <= ROUNDS; round++) {
  phase('Review')
  const review = await call('review', Object.assign({}, shared, {
    base: A.base,
    lenses: A.lenses,
    focus: round === 1 ? A.focus : 'only the changes made by the previous fix round, plus anything they broke',
    minSeverity: round === 1 ? A.minSeverity || 'minor' : 'major',
  }))
  if (!review.confirmed.length) {
    rounds.push({ round, confirmed: [], fix: null })
    break
  }
  phase('Fix')
  const fix = await call('fix', Object.assign({}, shared, { findings: review.confirmed, gates: A.gates }))
  rounds.push({ round, confirmed: review.confirmed, fix })
}

const last = rounds[rounds.length - 1]
const quiet = !!last && !last.confirmed.length
if (!quiet) log(`review-fix: stopped after ${rounds.length} round(s) with fixes not re-reviewed`)
return { quiet, rounds }
