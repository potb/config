---
name: stop-slop
description: Remove AI writing patterns from prose. Use when drafting, editing, or reviewing long-form text such as commit messages, docs, READMEs, PR descriptions, and published writing.
allowed-tools: read, write, edit, multiedit, grep, batch
metadata:
  trigger: Writing or editing persisted prose, reviewing a draft for AI tells
  author: Hardik Pandya (https://hvpandya.com)
  license: MIT
  source: https://github.com/hardikpandya/stop-slop
  upstream_commit: 8da1f030185bdfe8471220585162991eaeb970e9
  local_changes: >
    Flattened the upstream SKILL.md plus references/{phrases,structures,examples}.md
    into this single file, removed the duplicated adverb and em dash rules, added
    the Scope section below, replaced an em dash that appeared inside an upstream
    example, and softened the three-item list rule to a preference so it no longer
    contradicts the example that follows it.
---

# Stop Slop

Eliminate predictable AI writing patterns from prose.

## Scope

This skill governs persisted prose: commit messages, code comments, docs,
READMEs, issue and PR text, and anything published. The global prompt overlay in
`~/.jcode/prompt-overlay.md` governs chat replies, and it wins there. Do not
apply the rhythm and reader-in-the-room advice below to a terse chat answer.

The two agree where they overlap: no em dashes, no filler, no adverb padding.

## Core rules

1. **Cut filler phrases.** Remove throat-clearing openers, emphasis crutches,
   and adverbs. See Phrases below.

2. **Break formulaic structures.** Avoid binary contrasts, negative listings,
   dramatic fragmentation, rhetorical setups, and false agency. See Structures
   below.

3. **Use active voice.** Every sentence needs a human subject doing something.
   No passive constructions. No inanimate objects performing human actions ("the
   complaint becomes a fix").

4. **Be specific.** No vague declaratives ("The reasons are structural"). Name
   the specific thing. No lazy extremes ("every", "always", "never") doing vague
   work.

5. **Put the reader in the room.** No narrator-from-a-distance voice. "You"
   beats "People". Specifics beat abstractions.

6. **Vary rhythm.** Mix sentence lengths. Prefer two items over three. End
   paragraphs differently. No em dashes.

7. **Trust readers.** State facts directly. Skip softening, justification, and
   hand-holding.

8. **Cut quotables.** If it sounds like a pull-quote, rewrite it.

## Quick checks

Run these before delivering prose.

- Any adverbs? Kill them.
- Any passive voice? Find the actor, make them the subject.
- Inanimate thing doing a human verb ("the decision emerges")? Name the person.
- Sentence starts with a Wh- word? Restructure it.
- Any "here's what/this/that" throat-clearing? Cut to the point.
- Any "not X, it's Y" contrasts? State Y directly.
- Three consecutive sentences match length? Break one.
- Paragraph ends with a punchy one-liner? Vary it.
- Em dash anywhere? Remove it.
- Vague declarative ("The implications are significant")? Name the specific
  implication.
- Narrator-from-a-distance ("Nobody designed this")? Put the reader in the scene.
- Meta-joiners ("The rest of this essay...")? Delete them. Let the piece move.

## Phrases

### Throat-clearing openers

State the content directly instead.

- "Here's the thing:"
- "Here's what [X]" / "Here's this [X]" / "Here's that [X]" / "Here's why [X]"
- "The uncomfortable truth is"
- "It turns out"
- "The real [X] is"
- "Let me be clear"
- "The truth is,"
- "I'll say it again:"
- "I'm going to be honest"
- "Can we talk about"
- "Here's what I find interesting"
- "Here's the problem though"

Any "here's what/this/that" construction is throat-clearing before the point.
Cut it and state the point.

### Emphasis crutches

These add no meaning. Delete them.

- "Full stop." / "Period."
- "Let that sink in."
- "This matters because"
- "Make no mistake"
- "Here's why that matters"

### Business jargon

| Avoid | Use instead |
|-------|-------------|
| Navigate (challenges) | Handle, address |
| Unpack (analysis) | Explain, examine |
| Lean into | Accept, embrace |
| Landscape (context) | Situation, field |
| Game-changer | Significant, important |
| Double down | Commit, increase |
| Deep dive | Analysis, examination |
| Take a step back | Reconsider |
| Moving forward | Next, from now |
| Circle back | Return to, revisit |
| On the same page | Aligned, agreed |

### Adverbs and filler

Kill adverbs. No -ly words, no softeners, no intensifiers, no hedges. Frequent
offenders: really, just, literally, genuinely, honestly, simply, actually,
deeply, truly, fundamentally, inherently, inevitably, interestingly,
importantly, crucially.

Cut these filler phrases too.

- "At its core"
- "In today's [X]"
- "It's worth noting"
- "At the end of the day"
- "When it comes to"
- "In a world where"
- "The reality is"

### Meta-commentary

Remove self-referential asides. The piece should move, not announce its own
structure.

- "Hint:"
- "Plot twist:" / "Spoiler:"
- "You already know this, but"
- "But that's another post"
- "X is a feature, not a bug"
- "Dressed up as"
- "The rest of this essay explains..."
- "Let me walk you through..."
- "In this section, we'll..."
- "As we'll see..."
- "I want to explore..."

### Performative emphasis

False intimacy or manufactured sincerity: "creeps in", "I promise", "They
exist, I promise".

### Telling instead of showing

Announcing difficulty or significance rather than demonstrating it: "This is
genuinely hard", "This is what leadership actually looks like", "This is what X
actually looks like", "actually matters".

### Vague declaratives

Sentences that announce importance without naming the specific thing.

- "The reasons are structural"
- "The implications are significant"
- "This is the deepest problem"
- "The stakes are high"
- "The consequences are real"

If a sentence calls something important, deep, or structural without showing the
specific thing, cut it or replace it with the specific thing.

## Structures

### Binary contrasts

These create false drama.

| Pattern | Problem |
|---------|---------|
| "Not because X. Because Y." / "Not because X, but because Y." | Telegraphed reversal |
| "[X] isn't the problem. [Y] is." | Formulaic reframe |
| "The answer isn't X. It's Y." | Predictable pivot |
| "It feels like X. It's actually Y." | Setup and reveal cliche |
| "The question isn't X. It's Y." | Rhetorical misdirection |
| "Not X. But Y." / "not X, it's Y" / "isn't X, it's Y" | Mechanical contrast |
| "It's not this. It's that." | Same formula, different words |
| "stops being X and starts being Y" | False transformation arc |
| "doesn't mean X, but actually Y" | Negation-then-assertion crutch |
| "is about X but not Y" | False distinction |
| "not just X but also Y" | Additive hedge |

Instead: state Y directly. "The problem is Y." Drop the negation.

### Negative listing

Listing what something is not before revealing what it is. A rhetorical
striptease.

| Pattern | Problem |
|---------|---------|
| "Not a X... Not a Y... A Z." | Dramatic buildup through negation |
| "It wasn't X. It wasn't Y. It was Z." | Same structure, past tense |

Instead: state Z. The reader does not need the runway.

### Dramatic fragmentation

Sentence fragments for emphasis read as manufactured profundity.

| Pattern | Problem |
|---------|---------|
| "[Noun]. That's it. That's the [thing]." | Performative simplicity |
| "X. And Y. And Z." | Staccato drama |
| "This unlocks something. [Word]." | Artificial revelation |

Instead: complete sentences. Trust content over presentation.

### Rhetorical setups

These announce insight rather than deliver it.

| Pattern | Problem |
|---------|---------|
| "What if [reframe]?" | Socratic posturing |
| "Here's what I mean:" | Redundant preview |
| "Think about it:" | Condescending prompt |
| "And that's okay." | Unnecessary permission |

Instead: make the point and let readers draw conclusions.

### Formulaic constructions

| Pattern | Problem |
|---------|---------|
| "By the time X, I was Y." | Narrative template |
| "X that isn't Y" | Indirect. Say "X is broken" |

### False agency

Giving inanimate things human verbs. Complaints do not become fixes. Bets do not
live or die. Decisions do not emerge. A person does something to make those
things happen, and this pattern hides that person.

| Pattern | Problem |
|---------|---------|
| "a complaint becomes a fix" | The complaint did nothing. Someone fixed it. |
| "a bet lives or dies in days" | Bets have no lifespan. Someone kills the project or ships it. |
| "the decision emerges" | Someone decides. |
| "the culture shifts" | People change behavior. |
| "the conversation moves toward" | Someone steers. |
| "the data tells us" | Data sits there. Someone reads it and draws a conclusion. |
| "the market rewards" | Buyers pay for things. |

Instead: name the human. "The team fixed it that week" beats "the complaint
becomes a fix". If no specific person fits, use "you" to put the reader in the
seat.

### Narrator-from-a-distance

Floating above the scene instead of putting the reader in it.

| Pattern | Problem |
|---------|---------|
| "Nobody designed this." | Disembodied observation |
| "This happens because..." | Lecturer voice |
| "This is why..." | Lecturer voice |
| "People tend to..." | Armchair sociologist |

Instead: put the reader in the room. "You don't sit down one day and decide
to..." beats "Nobody designed this".

### Passive voice

Passive voice hides the actor and drains energy.

| Pattern | Fix |
|---------|-----|
| "X was created" | Name who created it |
| "It is believed that" | Name who believes it |
| "Mistakes were made" | Name who made them |
| "The decision was reached" | Name who decided |

### Sentence starters to avoid

| Pattern | Fix |
|---------|-----|
| Sentences starting with What, When, Where, Which, Who, Why, How | Restructure. Lead with the subject or the verb. |
| Paragraphs starting with "So" | Start with content |
| Sentences starting with "Look," | Remove it |

Wh- openers become a crutch. "What makes this hard is..." becomes "The
constraint is...", or better, name the specific constraint.

### Rhythm patterns

| Pattern | Fix |
|---------|-----|
| Three-item lists | Prefer two items, or one |
| Questions answered immediately | Let questions breathe, or cut them |
| Every paragraph ends punchily | Vary endings |
| Em dashes | Remove them. Use commas or periods. |
| Staccato fragmentation | Do not stack short punchy sentences |
| "Not always. Not perfectly." | Hedging disguised as reassurance |

### Word patterns

Lazy extremes (every, always, never, everyone, everybody, nobody) claim false
authority. Use specifics instead of sweeping claims.

## Examples

### Throat-clearing and binary contrast

Before:

> "Here's the thing: building products is hard. Not because the technology is
> complex. Because people are complex. Let that sink in."

After:

> "Building products is hard. Technology is manageable. People aren't."

Removed the opener, the binary contrast, and the emphasis crutch.

### Filler and unnecessary reassurance

Before:

> "It turns out that most teams struggle with alignment. The uncomfortable truth
> is that nobody wants to admit they're confused. And that's okay."

After:

> "Teams struggle with alignment. Nobody admits confusion."

Cut the hedging, the throat-clearing, and the permission-granting ending.

### Business jargon stack

Before:

> "In today's fast-paced landscape, we need to lean into discomfort and navigate
> uncertainty with clarity. This matters because your competition isn't waiting."

After:

> "Move faster. Your competition is."

Eliminated the jargon. Core message in six words.

### Dramatic fragmentation

Before:

> "Speed. Quality. Cost. You can only pick two. That's it. That's the tradeoff."

After:

> "Speed, quality, cost: pick two."

One sentence, no performative emphasis.

### Rhetorical setup

Before:

> "What if I told you that the best teams don't optimize for productivity?
> Here's what I mean: they optimize for learning. Think about it."

After:

> "The best teams optimize for learning, not productivity."

Direct claim, no rhetorical scaffolding.

## Scoring

Rate 1-10 on each dimension.

| Dimension | Question |
|-----------|----------|
| Directness | Statements or announcements? |
| Rhythm | Varied or metronomic? |
| Trust | Respects reader intelligence? |
| Authenticity | Sounds human? |
| Density | Anything cuttable? |

Below 35/50, revise.
