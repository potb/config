export const meta = {
  name: 'block-design',
  description: 'Building block: turn a goal and facts into a plan of units with file ownership and difficulty',
  whenToUse: 'design("goal") or design({goal, facts, angles}) before build',
  phases: [
    { title: 'Design', detail: 'one fable designer, or one per angle' },
    { title: 'Judge', detail: 'fable picks the best design and grafts the rest (only with several angles)' },
  ],
}

const A = typeof args === 'string' ? { goal: args } : (args || {})
if (!A.goal) throw new Error('design: goal is required')
const M = Object.assign({ designer: 'fable', judge: 'fable' }, A.models)
const CTX = [
  A.cwd && `Working directory: ${A.cwd}.`,
  A.profile && `Read the project profile at ${A.profile} first and respect every repo principle in it.`,
  A.context,
  'Read-only: never edit, commit or push. Use fd and rg.',
].filter(Boolean).join('\n')

const DESIGN = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    units: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          brief: { type: 'string', description: 'what to build, test first, acceptance criteria' },
          owns: { type: 'array', items: { type: 'string' }, description: 'files or globs only this unit may edit' },
          hard: { type: 'boolean', description: 'true when it needs the strongest model' },
          dependsOn: { type: 'array', items: { type: 'string' } },
        },
        required: ['id', 'title', 'brief', 'owns', 'hard', 'dependsOn'],
      },
    },
    decisions: { type: 'array', items: { type: 'string' } },
    risks: { type: 'array', items: { type: 'string' } },
    ownerQuestions: { type: 'array', items: { type: 'string' }, description: 'decisions only the owner can make; empty if none' },
  },
  required: ['summary', 'units', 'decisions', 'risks', 'ownerQuestions'],
}

const base = `${CTX}\nDesign how to reach this goal. Split it into units that can be built in parallel with disjoint file ownership; mark dependencies and which units are hard. Put shared contracts (types, schemas, migrations) in their own first unit.\nGOAL: ${A.goal}\n${A.facts ? 'FACTS: ' + JSON.stringify(A.facts) : ''}`
const angles = A.angles && A.angles.length ? A.angles : null

phase('Design')
if (!angles) {
  const design = await agent(base, { label: 'design', phase: 'Design', schema: DESIGN, model: M.designer, effort: 'high' })
  return { goal: A.goal, design }
}
const drafts = (await parallel(angles.map(a => () => agent(`${base}\nDesign from this angle: ${a}.`, {
  label: `design:${a}`.slice(0, 40), phase: 'Design', schema: DESIGN, model: M.designer,
}).then(d => d && Object.assign({ angle: a }, d))))).filter(Boolean)

phase('Judge')
const design = await agent(
  `${CTX}\nJudge these competing designs for the goal. Pick the strongest, graft the best ideas from the others, and return one final design.\nGOAL: ${A.goal}\nDESIGNS: ${JSON.stringify(drafts)}`,
  { label: 'judge', phase: 'Judge', schema: DESIGN, model: M.judge, effort: 'high' },
)
return { goal: A.goal, design, drafts }
