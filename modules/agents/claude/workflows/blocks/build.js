export const meta = {
  name: 'block-build',
  description: 'Building block: build each unit test-first, one agent per unit, respecting dependencies',
  whenToUse: 'build({units, cwd, base, gates}) with units from design',
  phases: [{ title: 'Build', detail: 'opus for hard units, sonnet otherwise; worktree per unit by default' }],
}

const A = args || {}
if (!A.units || !A.units.length) throw new Error('build: units are required')
const M = Object.assign({ hard: 'opus', easy: 'sonnet' }, A.models)
const WORKTREE = A.worktree !== false
const CTX = [
  A.cwd && `Repository: ${A.cwd}.`,
  A.base && `Base branch: ${A.base}.`,
  A.profile && `Read the project profile at ${A.profile} first and follow its gates and rules.`,
  A.context,
  A.gates && A.gates.length && `Gates that must pass before you are done: ${A.gates.join(' && ')}`,
  'Use fd and rg. Never push, never open PRs, never merge.',
  'Report only checks you actually ran, with their real result.',
].filter(Boolean).join('\n')

const RESULT = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'partial', 'blocked'] },
    branch: { type: 'string', description: 'branch holding the commit, empty if none' },
    commit: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    gatesRun: { type: 'array', items: { type: 'string' }, description: 'command and pass or fail' },
    notes: { type: 'string', description: 'blockers, deviations from the brief, follow-ups' },
  },
  required: ['status', 'branch', 'commit', 'filesChanged', 'gatesRun', 'notes'],
}

const byId = {}
for (const u of A.units) byId[u.id] = u
const running = {}
const run = u => {
  if (running[u.id]) return running[u.id]
  const deps = (u.dependsOn || []).filter(d => byId[d]).map(d => run(byId[d]))
  running[u.id] = Promise.all(deps).then(depResults => agent(
    `${CTX}\nBuild one unit. Write the failing test first, then the minimal change, then run every gate. Edit only files you own. Commit once on a branch named build/${u.id} with a clear message.\nUNIT ${u.id}: ${u.title}\nBRIEF: ${u.brief}\nYOU OWN: ${(u.owns || []).join(', ') || 'see brief'}\n${depResults.length ? 'DEPENDENCIES ALREADY BUILT: ' + JSON.stringify(depResults) : ''}`,
    Object.assign(
      { label: `build:${u.id}`.slice(0, 40), phase: 'Build', schema: RESULT, model: u.hard ? M.hard : M.easy },
      WORKTREE ? { isolation: 'worktree' } : {},
    ),
  ).then(r => Object.assign({ id: u.id }, r || { status: 'blocked', notes: 'agent returned nothing' })))
  return running[u.id]
}

phase('Build')
const results = await Promise.all(A.units.map(run))
const blocked = results.filter(r => r.status !== 'done')
if (blocked.length) log(`build: ${blocked.length} unit(s) not done: ${blocked.map(r => r.id).join(', ')}`)
return { results, branches: results.filter(r => r.branch).map(r => r.branch), blocked }
