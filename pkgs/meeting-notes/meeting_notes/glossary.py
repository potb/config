import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from . import notify as notify_module
from . import opencode, state

LOG = logging.getLogger(__name__)

CANDIDATES = "glossary-candidates.json"
GLOSSARY = "pkgs/meeting-notes/glossary.md"
MAX_CANDIDATES = 30
MAX_TEXT = 200
MAX_LINES = 4
MAX_LINE = 400
STAMP = re.compile(r"^\[(\d\d:\d\d:\d\d)\]")
KINDS = ("nom", "produit", "fournisseur", "entreprise", "terme", "reconnaissance")
NOTIFY_TITLE = "meeting-notes"
BLOCKED_READS = ("*.npz", "*.png", "*.jpg", "*.wav", "*.env", "*.env.*")


class GlossaryError(RuntimeError):
    pass


def _text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:MAX_TEXT]


def _texts(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [text for text in (_text(item) for item in value) if text][:MAX_LINES]


def known(term, glossary_text):
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", glossary_text, re.I) is not None


def load_candidates(path, glossary_text=""):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as error:
        raise GlossaryError(f"{path} is not valid JSON: {error}") from None
    if isinstance(data, dict):
        data = data.get("candidates")
    if not isinstance(data, list):
        raise GlossaryError(f"{path} must hold a list of candidates")
    out, seen = [], set()
    for item in data:
        if not isinstance(item, dict):
            continue
        term = _text(item.get("term"))
        heard = [h for h in _texts(item.get("heard")) if h.lower() != term.lower()]
        if not term or term.lower() in seen:
            continue
        if known(term, glossary_text) and all(known(h, glossary_text) for h in heard):
            continue
        seen.add(term.lower())
        kind = _text(item.get("kind")).lower()
        out.append(
            {
                "term": term,
                "heard": heard,
                "kind": kind if kind in KINDS else "terme",
                "sure": item.get("sure") is True,
                "lines": [s for s in _texts(item.get("lines")) if re.fullmatch(r"\d\d:\d\d:\d\d", s)],
                "note": _text(item.get("note")),
            }
        )
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def excerpt(line, words):
    if len(line) <= MAX_LINE:
        return line
    head = line.split("|", 1)[0] + "| "
    lower = line.lower()
    found = [lower.find(word) for word in words if word and lower.find(word) >= len(head)]
    if not found:
        return line[:MAX_LINE] + "..."
    start = max(len(head), min(found) - MAX_LINE // 2)
    end = min(len(line), start + MAX_LINE - len(head))
    return head + ("..." if start > len(head) else "") + line[start:end] + ("..." if end < len(line) else "")


def context(transcript_lines, candidate):
    stamps = set(candidate["lines"])
    words = [w.lower() for w in candidate["heard"] + [candidate["term"]]]
    picked = []
    for line in transcript_lines:
        match = STAMP.match(line)
        hit = match and match.group(1) in stamps
        if hit or any(word in line.lower() for word in words):
            picked.append(excerpt(line, words))
        if len(picked) >= MAX_LINES:
            break
    return picked


def session_title(title, date):
    if title.endswith(date):
        return f"glossaire {title}"
    return f"glossaire {title} {date}"


def model_ref(notes_model):
    if not notes_model or "/" not in notes_model:
        return None
    provider, _, rest = notes_model.partition("/")
    model, _, variant = rest.partition("#")
    ref = {"providerID": provider, "id": model}
    if variant:
        ref["variant"] = variant
    return ref


def permissions(repo, readable):
    rule = lambda effect, action, resource: {"action": action, "resource": resource, "effect": effect}
    glossary = str(Path(repo) / GLOSSARY)
    rules = [
        rule("deny", "*", "*"),
        rule("allow", "read", GLOSSARY),
        rule("allow", "read", glossary),
    ]
    for folder in readable:
        rules.append(rule("allow", "external_directory", f"{folder}/*"))
        rules.append(rule("allow", "read", f"{folder}/*"))
    rules += [rule("deny", "read", pattern) for pattern in BLOCKED_READS]
    rules += [rule("ask", "edit", GLOSSARY), rule("ask", "edit", glossary)]
    return rules


def _candidate_block(index, candidate, lines):
    head = f"{index}. **{candidate['term']}** ({candidate['kind']}"
    if candidate["heard"]:
        head += ", entendu : " + ", ".join(f"« {h} »" for h in candidate["heard"])
    head += ", sûr" if candidate["sure"] else ", pas sûr"
    head += ")"
    if candidate["note"]:
        head += f" : {candidate['note']}"
    body = [f"   {line}" for line in lines] or ["   (aucune ligne trouvée dans transcript.txt)"]
    return "\n".join([head, *body])


def message(meeting_title, date, candidates, transcript_lines, glossary_text, files):
    blocks = [
        _candidate_block(i, c, context(transcript_lines, c)) for i, c in enumerate(candidates, 1)
    ]
    listing = "\n".join(f"- `{path}`" for path in files)
    return f"""Après la réunion « {meeting_title} » du {date}, le run des notes a relevé {len(candidates)} \
termes candidats pour le glossaire des notes de réunion : noms propres, produits, fournisseurs ou \
mauvaises reconnaissances qu'il a corrigés ou dont il n'était pas sûr.

## Candidats, avec leurs lignes de transcript.txt

{chr(10).join(blocks)}

## Glossaire actuel (`{GLOSSARY}`)

```markdown
{glossary_text.rstrip()}
```

## Fichiers de la réunion, en lecture seule

{listing}

## Ta tâche

1. Pour chaque candidat, vérifie le contexte (relis le transcript si besoin) et propose la ligne \
exacte à ajouter à `{GLOSSARY}`, au format des lignes existantes, ou dis pourquoi ne pas l'ajouter \
(terme courant, nom de passage, doute).
2. Puis arrête-toi et attends ma réponse. Ne modifie pas le glossaire avant que j'aie validé.
3. Après ma validation, ajoute seulement les lignes validées, et rien d'autre, dans `{GLOSSARY}`.

Tu ne peux lire que ce glossaire et les fichiers listés, et n'écrire que dans le glossaire, après \
mon accord. Pas de shell, pas de commit : je committe moi-même. Ce fichier est une copie locale \
non suivie par git : une modification ne prend effet pour les prochaines réunions qu'après \
`scripts/private-data`, commit et switch."""


def _payload(cfg, title, repo, readable):
    body = {"title": title, "location": {"directory": str(repo)}, "permissions": permissions(repo, readable)}
    ref = model_ref(cfg.notes_model)
    if ref:
        body["model"] = ref
    return body


def api_post_argv(cfg, path, body):
    return [cfg.opencode, "api", "post", path, "--data", json.dumps(body, ensure_ascii=False)]


def service_argv(cfg):
    return [cfg.opencode, "service", "status"]


def _data(text):
    try:
        data = json.loads(text)
    except ValueError:
        return None
    data = data.get("data") if isinstance(data, dict) else None
    return data if isinstance(data, dict) else None


def service_up(run, cfg, cwd, scratch):
    code, text = opencode.capture(run, service_argv(cfg), cwd, scratch)
    return code == 0 and "http" in text


def create_session(run, cfg, title, repo, readable, text, scratch):
    code, out = opencode.capture(run, api_post_argv(cfg, "/api/session", _payload(cfg, title, repo, readable)), repo, scratch)
    created = _data(out)
    if code or not created or not isinstance(created.get("id"), str):
        raise GlossaryError(f"session create failed ({code}): {out.strip()[:300]}")
    sid = created["id"]
    code, out = opencode.capture(run, api_post_argv(cfg, f"/api/session/{sid}/prompt", {"text": text}), repo, scratch)
    if code or not _data(out):
        raise GlossaryError(f"session {sid} created but the first message failed ({code}): {out.strip()[:300]}")
    return sid


def announcement(count, meeting_title, title, repo_label, sid):
    return (
        f"{count} termes candidats pour le glossaire après {meeting_title}. "
        f"Ouvre la session OpenCode \"{title}\" dans {repo_label} pour les valider (session {sid})."
    )


def fallback_announcement(count, meeting_title, mid):
    return (
        f"{count} termes candidats pour le glossaire après {meeting_title}. "
        f"Le service OpenCode ne répond pas : lance `meeting-notes glossary {mid}` pour ouvrir la session."
    )


def repo_label(repo, home):
    try:
        return "~/" + str(Path(repo).relative_to(home))
    except ValueError:
        return str(repo)


def announce(cfg, run, text, slack_module=None, notify=notify_module, sensitive=False):
    if cfg.slack and not sensitive:
        if slack_module is None:
            from . import slack as slack_module
        try:
            slack_module.post_dm(cfg, text)
            return "slack"
        except Exception as error:
            LOG.warning("glossary DM failed, desktop notification instead: %s", error)
    notify.send(NOTIFY_TITLE, text, run)
    return "desktop"


def _local_date(moment):
    parsed = datetime.strptime(moment, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%Y-%m-%d")


def notes_title(folder, fallback):
    try:
        first = Path(folder, "notes.md").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return fallback
    return first[2:].strip() if first.startswith("# ") and first[2:].strip() else fallback


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def propose(cfg, mid, run, scratch, slack_module=None, notify=notify_module, force=False, home=None):
    repo = cfg.glossary_repo
    if repo is None:
        return None
    with state.locked(cfg.state_path) as st:
        meeting = st["meetings"].get(mid) or {}
        info = dict(state.processed(st, mid) or {})
    if not force and info.get("glossary_session"):
        return None
    if info.get("status") in (state.SKIPPED, state.SKIPPED_SHORT, state.FAILED, None):
        return None
    sensitive = bool(info.get("sensitive"))
    work = cfg.meeting_dir(mid)
    if not (Path(repo) / GLOSSARY).is_file():
        LOG.warning("glossary repo %s has no %s, no glossary session for %s", repo, GLOSSARY, mid)
        return None
    glossary_text = _read(Path(repo) / GLOSSARY)
    candidates = load_candidates(work / CANDIDATES, glossary_text)
    if not candidates:
        return None
    folder = info.get("dir")
    meeting_title = notes_title(folder, meeting.get("title") or mid) if folder else meeting.get("title") or mid
    date = _local_date(meeting["start"]) if meeting.get("start") else mid[:8]
    title = session_title(meeting_title, date)
    files = [str(work / "transcript.txt"), str(work / "meta.json"), str(work / CANDIDATES)]
    readable = [str(work)]
    if folder:
        files += [str(Path(folder) / "notes.md"), str(Path(folder) / "transcript.md")]
        readable.append(str(folder))
    text = message(meeting_title, date, candidates, _read(work / "transcript.txt").splitlines(), glossary_text, files)
    label = repo_label(repo, home or Path.home())
    if not service_up(run, cfg, repo, scratch):
        announce(cfg, run, fallback_announcement(len(candidates), meeting_title, mid), slack_module, notify, sensitive)
        return None
    sid = create_session(run, cfg, title, repo, readable, text, scratch)
    with state.locked(cfg.state_path) as st:
        current = dict(state.processed(st, mid) or {})
        current.update(glossary_session=sid, glossary_candidates=len(candidates))
        st["processed"][mid] = current
    channel = announce(cfg, run, announcement(len(candidates), meeting_title, title, label, sid), slack_module, notify, sensitive)
    LOG.info("glossary session %s for %s (%s candidates, told by %s)", sid, mid, len(candidates), channel)
    return sid
