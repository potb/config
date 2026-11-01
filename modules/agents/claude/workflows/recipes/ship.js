export const meta = {
  name: 'recipe-ship',
  description: 'Recipe: design, build in parallel, gate, review and fix, then open a draft PR; stops at owner questions',
  whenToUse: 'ship({goal, cwd, base, gates, profile}) for a feature that ships as one branch and one PR',
  phases: [
    { title: 'Design', detail: 'block-design (skipped when units are given)' },
    { title: 'Build', detail: 'block-build' },
    { title: 'Gate', detail: 'block-gate merges unit branches and gets the tree green' },
    { title: 'Review', detail: 'block-review then block-fix, bounded rounds' },
    { title: 'Land', detail: 'block-land, draft PR, never merges' },
  ],
}

const A = args || {}
if (!A.cwd || !A.base) throw new Error('ship: cwd and base are required')
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
const STAGES = ['design', 'build', 'gate', 'review', 'land']
const STOP = STAGES.indexOf(A.stopAfter || 'land')
const out = { stoppedAt: null }

let units = A.units
if (!units) {
  phase('Design')
  const d = await call('design', Object.assign({}, shared, { goal: A.goal, facts: A.facts, angles: A.angles }))
  out.design = d.design
  units = d.design.units
  if (d.design.ownerQuestions.length && !A.autonomous) {
    out.stoppedAt = 'design: owner questions'
    return out
  }
}
if (STOP === 0) return Object.assign(out, { stoppedAt: 'design' })

phase('Build')
out.build = await call('build', Object.assign({}, shared, { units, base: A.base, gates: A.gates, worktree: A.worktree }))
if (out.build.blocked.length && !A.autonomous) return Object.assign(out, { stoppedAt: 'build: blocked units' })
if (STOP === 1) return Object.assign(out, { stoppedAt: 'build' })

phase('Gate')
out.gate = await call('gate', Object.assign({}, shared, { gates: A.gates, e2e: A.e2e, branches: out.build.branches }))
if (!out.gate.green) return Object.assign(out, { stoppedAt: 'gate: red' })
if (STOP === 2) return Object.assign(out, { stoppedAt: 'gate' })

phase('Review')
out.reviews = []
const ROUNDS = A.maxReviewRounds || 2
for (let round = 1; round <= ROUNDS; round++) {
  const review = await call('review', Object.assign({}, shared, {
    base: A.base,
    lenses: A.lenses,
    minSeverity: round === 1 ? 'minor' : 'major',
    focus: round === 1 ? A.focus : 'only the changes made by the previous fix round, plus anything they broke',
  }))
  if (!review.confirmed.length) {
    out.reviews.push({ round, confirmed: [], fix: null })
    break
  }
  const fix = await call('fix', Object.assign({}, shared, { findings: review.confirmed, gates: A.gates }))
  out.reviews.push({ round, confirmed: review.confirmed, fix })
}
const lastReview = out.reviews[out.reviews.length - 1]
if (lastReview.confirmed.length) log(`ship: review not quiet after ${out.reviews.length} round(s)`)
if (STOP === 3) return Object.assign(out, { stoppedAt: 'review' })

phase('Land')
out.land = await call('land', Object.assign({}, shared, { base: A.base, title: A.title, ready: A.ready, screenshots: A.screenshots }))
out.stoppedAt = 'land'
return out
