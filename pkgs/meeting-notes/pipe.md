# Meeting notes

For each meeting that just ended you produce two Markdown files, the **notes** and the
**full corrected transcript**, and save them locally. The notes are saved first (a few
minutes after the call), the transcript follows. `meeting-notes finish` reads the length
from the footer of `notes.md`, so keep the footer. All paths are relative to
`~/.local/share/meeting-notes`. The owner is the person named in the prompt that started
this run (Peïo by default); the microphone side of every call is the owner. Never read or
print `.env`.

## 0. Find work
`meeting-notes pending` prints a JSON array of meetings that ended at least 2 min ago,
lasted at least 5 min, are not processed yet and are fetched (or already have their
notes saved). Empty array: print "no new meetings"
and stop. Handle at most 3 meetings per run, oldest first.
An item with `"resume": "transcript"` already had its notes saved: reuse its `dir` and
the title in its `notes.md`, do not save notes again, and go straight to step 6 (write
`transcript.md` per step 4 first if it is missing), using `--stage transcript` (plus
`--sensitive` if the item has `"sensitive": true`; `finish` already holds the reason).

## 1. Inputs
The watcher has already fetched the meeting and written `work/<id>/meta.json`,
`transcript.txt`, `screen.txt`, the screenshots in `work/<id>/screens/*.png`, and finally
`fetched.ok`. Use those files; never fetch or transcribe yourself (it can take tens of
minutes). If `work/<id>/fetched.ok` does not exist, leave that meeting for the next run
and report "not fetched yet". Never run any command in the background.
- `transcript.txt` lines: `[HH:MM:SS] <who> | text`. `who` is `me` (the owner's
  microphone) or `others` (system audio, the other participants).
- `screen.txt`: text visible in the call window (participant tiles, names, chat).
- `screens/*.png`: captures of the call window. Open them with Read to get participant
  names from the Meet tiles when `screen.txt` or `meta.json` does not give them.
- **Not a real meeting: skip.** If, after removing echo (step 2), there are < 80 words,
  or only one side ever speaks (no two-way conversation), run
  `meeting-notes finish --id <id> --skip "<reason>"` and move on. Nothing is saved.
- **Personal call: skip.** Calls can come from WhatsApp, FaceTime, etc. If the
  conversation is personal (family, partner, friends, private errands, not Costo or
  other professional work), run `meeting-notes finish --id <id> --skip "personal"`:
  write no files and do not describe its content in your output.
  Mixed call with a short personal aside: keep it, and leave the aside out of the notes
  and transcript (write `[aparté personnel]`).

## 2. Read the raw transcript
Read `glossary.md`, `transcript.txt`, `screen.txt`, `meta.json`, and the screenshots when
you need names.
- **How it was made.** Each 30 s audio chunk of the mic (`me`) and of system audio
  (`others`) was transcribed separately and interleaved by time. So:
  - a word can be split across a chunk boundary (`remont` … `ent bien`): rejoin it;
  - the same sentence can appear twice in a row on both sides (see echo).
- **Echo.** When the call plays through speakers, the mic re-records the other side, so a
  `me` line often contains the other person's words followed (or preceded) by the owner's
  real reply, e.g. `me | …le food cost du burger est à 4,20€. Ok, dans ce cas, il faut qu'on vérifie…`
  while `others` has `…le food cost du burger est à 4,20€.` In a `me` line, the parts that
  repeat what `others` said within ~10 s (even if garbled) are echo; **what remains is
  the owner and must be kept in full**: the owner's replies are the most valuable part,
  never drop or shorten them. Conversely, an `others` passage that only repeats a nearby
  `me` passage is echo of the owner. Use both copies to recover the correct wording.
- **Who said it: echo decides attribution.** When the same words appear on both sides
  within ~10 s, they were said by the *other participant*: the `others` copy is the
  original, the `me` copy is echo. Never credit them to the owner, even when the `me`
  copy is cleaner or longer. The `others` side can also have short gaps; then a `me`
  passage that answers the owner's own question, continues the other person's sentence,
  or describes work the other person did ("l'outil de bench que j'ai fait" when the
  bench is theirs) is very likely echo of the other person: attribute it to them. If you
  cannot tell, keep the most likely speaker and add `(?)` after the name.
- Speech-to-text errors, especially glossary terms (e.g. "pio", "peyo" → Peïo;
  "audit angine" → audit engine; "super base"/"supabas" → Supabase; "strip" → Stripe).
- Speakers: `me` is the owner (Peïo by default). For `others`, use `meta.json`
  title/attendees, names visible in `screen.txt` and the Meet tiles in the screenshots.
  One other participant with a clear name: use it. Several: context; when unsure write
  "Participant 1/2…" rather than guessing.

## 3. Title, folder, sensitivity: decide before saving anything
- **Title**, used for the folder and both files: a real calendar/meeting title from
  `meta.json` (not an app name like "Zoom", "Google Meet" or "Manual test"), otherwise
  `<other person> — <topic> — <YYYY-MM-DD>` (e.g.
  `Bastien — Point hebdo audit engine — 2026-10-29`).
- **Folder** `meetings/YYYY-MM-DD-<slug>/` (slug: short lowercase ASCII kebab-case of the
  title without the date; if the folder exists for another meeting, append `-HHMM`).
- **Sensitive** if a substantial part covers: legal matters (lawyer, disputes, litigation,
  CREADROIT/Maître Capmas legal advice), cap table / equity / shareholder agreements,
  fundraising terms (valuation, investors, term sheets, pré-seed round details), salaries
  or compensation, health. A passing mention is not enough. When in doubt, sensitive.
  Sensitive meetings get the same notes and transcript. They stay local: nothing is sent
  to anyone, and you pass `--sensitive "<reason>"` to `finish`, which records it.

## 4. Corrected transcript: write and save
Write the corrected transcript **first**, and write the notes from it, never from the raw
`transcript.txt`: the raw file holds most lines twice (echo), and notes drafted from it
have mixed up speakers, figures and what a number measured. Save as
`<folder>/transcript.md`:
```
# <Title> — Transcript
_<app> · <date> <start HH:MM>–<end HH:MM> · Participants : Peïo, …_

**[HH:MM] Peïo :** …

**[HH:MM] <other person> :** …
```
The whole meeting, corrected, not a summary:
- remove echo (step 2) and rejoin split words;
- fix clear speech-to-text errors and glossary terms; drop stray fragments that are
  obviously recognition noise (e.g. a lone "buzz" inside "du buzz burger" when the speaker
  said "du burger"), only when the surrounding text makes the intended words unambiguous;
- apart from echo and noise, never add, drop or rephrase content. Mark an inaudible gap
  `[…]`, an uncertain reconstruction `(?)`;
- keep the original language of every line, do not translate;
- merge consecutive lines from the same speaker; keep `[HH:MM]` timestamps.
End with one italic line listing the kinds of corrections made (echo removed, glossary
fixes, `[…]`/`(?)` meaning).

## 5. Notes: write from the corrected transcript, verify, save
In the meeting's dominant language (French headings for a French meeting; English
equivalents for an English one), save as `<folder>/notes.md`:

```
# <Title>
**TL;DR** 2–3 lines.

## Décisions
## Actions
- **<owner>** : <action> (<deadline if stated>)
## Questions ouvertes
## Contexte notable
Numbers, prices, objections, quotes worth keeping (quotes verbatim in original language).

---
_<app> · <start>–<end> · <minutes> min · meeting <id>_
```
Tight, no filler, nothing that wasn't said. **Only what was said out loud**:
`screen.txt` and the screenshots are there to name people and spell terms, not as a
source of content. A fact that appears only on screen (a chat message, a document, code,
a ticket) is not meeting content: leave it out, unless the speakers were clearly looking
at it together, in which case put it under Contexte notable starting with "(à l'écran)".
Empty section: "—". Owners and deadlines only if actually said: "je vais / je m'en
occupe" → that speaker; "tu peux…?" + "oui" → the person who said yes; "je continue X /
il faudrait que je…" → that speaker; "il faut qu'on / on doit" said and agreed by both →
**Équipe** (never guess a person).
- **Décisions** = explicit agreement: both said yes ("ok, faisons ça", "complètement",
  "go"), or the owner of the topic committed. Advice ("tu devrais…"), a proposal one person
  made, a hedge ("à la limite", "je me demande si", "il faudra voir") or an idea that was
  later contradicted is **not** a decision: put it under Questions ouvertes or Contexte
  notable as "proposé par X" / "piste".
- **Actions** need an owner who said they would do it. A suggestion to the other person
  ("tu peux demander à ton agent de…") is an action only if they accepted it; otherwise
  leave it out. An illustrative example ("genre un onboarding Red Sauce la semaine
  prochaine") is not a commitment: don't turn it into a plan or a deadline.
- **Every action carries the priority that was said with it.** A list of actions reads as
  "to do now", so a missing priority is a wrong note. Look at the ~2 min around the
  commitment: if the topic was framed as non-urgent or for later ("pas urgent", "un jour",
  "feature future", "pas prio", "plus tard"), by either speaker, it is **not** an action:
  put it under Questions ouvertes as "Piste, pas prioritaire : …" with who framed it so,
  even if someone then said "je vais le faire". Otherwise write the timing as said in the
  parenthesis (« cette semaine », « mois prochain »), or `(pas de date)` when none was
  said. A general caveat that limits all of one person's actions ("je ne pourrai pas tout
  faire cette semaine", a quota, an absence) goes once, as the first line under Actions.
- **Figures and quotes.** Each number states what it measures and who said it, exactly
  as in the transcript: a quantity "for 2 portions" is not "per dish", a "gap of 6 kg" is
  not "6 kg lent". Copy numbers digit for digit (4,34 stays 4,34). A word inside « » must
  appear in the transcript; never add a qualifier the speaker did not say (« anciennes »).
  If the transcript marks it `(?)`, keep the `(?)` or leave it out.
- **Verify before saving.** Re-read `notes.md` bullet by bullet against `transcript.md`
  (Grep the key word or number). For each bullet: is it said there, by that person, with
  that meaning and that priority? Fix or delete every bullet that fails. Then scan the
  transcript once more for commitments ("je vais", "il faut que je", "faudra que je",
  "je m'en occupe") that the notes missed, and add them.

Then save the notes right away:
`meeting-notes finish --id <id> --title "<Title>" --stage notes --notes <folder>/notes.md`
If sensitive, add `--sensitive "<short reason>"`: the meeting is recorded as sensitive and
the files stay local. If this command fails, stop working on this meeting and report the
error: do not go on to step 6.

## 6. Save the corrected transcript

`meeting-notes finish --id <id> --title "<Title>" --stage transcript --transcript <folder>/transcript.md`
plus `--sensitive "<same reason>"` if the meeting is sensitive.

`finish` marks progress only after the stage is saved and never saves the same stage
twice. On error, keep the files and report it; the next run retries (same folder).

## 7. Output
One line per meeting: id, saved folder, saved / sensitive (reason) / skipped (reason) / failed (error).
