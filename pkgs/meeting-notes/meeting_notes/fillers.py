import json
import re
from pathlib import Path

TURN = re.compile(r"^(\*\*\[(?:[01]?\d|2[0-3]):[0-5]\d\]\s*(.+?)\s*:\*\*\s*)(.*)$")
LETTERS = r"\wÀ-ÿ'’-"
TOKEN = re.compile(rf"[{LETTERS}]+")
SENTENCE = re.compile(r"[^.?!…]+(?:[.?!…]+|$)")
STOPS = ".?!…"
MAX_ACK_TOKENS = 4

ACK_PHRASES = (
    "ah d'accord",
    "ah ouais",
    "ah ok",
    "d'accord",
    "okay",
    "ouais",
    "ouai",
    "mhm",
    "yes",
    "oui",
    "ok",
    "ah",
    "oh",
    "hm",
    "mh",
)
STRONG = re.compile(
    r"\b(exactement|ça marche|bien sûr|carrément|clairement|tout à fait|complètement|parfait|vas-y|go|d'accord pour)\b"
)
PROPOSAL = re.compile(
    r"\b(on (peut|pourrait|fait|va|se)|tu (peux|pourrais|veux|voudrais)|vous (pouvez|voulez)|"
    r"je (propose|te propose|peux|vais)|faut qu'on|il faut|ça te va|ça vous va|ok pour|"
    r"vas-y|d'accord pour|on se retrouve|on se voit|on reste)\b"
)
NEGATIVE = {"non", "nan", "pas", "jamais", "rien", "personne", "aucun", "aucune", "ne", "n'", "ni"}
KEEP_REPEATED = {
    "faire",
    "nous",
    "vous",
    "très",
    "trop",
    "beaucoup",
    "vraiment",
    "plus",
    "encore",
    "toujours",
    "vite",
    "bien",
    "si",
    "oui",
    "non",
    "là",
    "ah",
    "oh",
    "allez",
    "attends",
    "attention",
    "moi",
    "toi",
    "lui",
    "eux",
    "ciao",
    "bye",
    "merci",
    "hop",
}
REPEAT = re.compile(rf"(?<![{LETTERS}])((?:[{LETTERS}]+ +){{0,2}}[{LETTERS}]+)(?: +\1)+(?![{LETTERS}])", re.I)
TU_VOIS_OBJECT = re.compile(r"\s*(ce|le|la|les|un|une|ça|si|comment|pourquoi|quoi|qu|que|pas|bien|où)\b")
EN_GROS_TRADE = re.compile(r"(acheter|achète|achat|vendre|vend|vente|commerce|prix|marchand|grossiste)\s*$")
QUOI_KEEP_BEFORE = re.compile(r"\b(c'est|de|à|pour|sur|en|par|ou|sais|savoir|est|fait|faire|fais|que|dis|dit)\s*$")
GENRE_KEEP_BEFORE = re.compile(r"\b(un|le|ce|du|quel|quelle|de|mon|ton|son|même|bon|nouveau|autre|mauvais)\s*$")
START = rf"(?<![{LETTERS}])"
DU_COUP_STRIP = re.compile(r"(\s*,?\s*\b(en gros|tu vois|en fait|quoi)\b\s*,?)+$")


def norm(text):
    return text.replace("’", "'").lower()


def tokens(text):
    return TOKEN.findall(norm(text))


def _quoted(text, pos):
    return text[:pos].count("«") > text[:pos].count("»")


def _overlaps(cuts, start, end):
    return any(start < b and a < end for a, b, _ in cuts)


def _keep_du_coup(low, start, end):
    before = DU_COUP_STRIP.sub("", low[:start].rstrip()).rstrip()
    after = low[end:]
    if re.search(r"\bet après\s*,?$", before):
        return True
    if re.search(r"\bdonc$", before):
        return False
    return not (before.endswith(",") and after.lstrip().startswith(",") and not re.search(r"\b(et|mais)\s*,?$", before))


def _keep_genre(low, start, end):
    before, after = low[:start], low[end:]
    if GENRE_KEEP_BEFORE.search(before) or re.match(r"\s*(de|d')\b", after):
        return True
    window = tokens(after[:40])[:5]
    return any(re.search(r"\d", w) or w in ("en", "je", "un", "une") for w in window[:2]) or any(
        re.search(r"\d", w) for w in window
    )


def filler_cuts(text):
    low = norm(text)
    cuts = []

    def add(start, end, kind):
        if not _quoted(text, start) and not _overlaps(cuts, start, end):
            cuts.append((start, end, kind))

    for m in re.finditer(START + r"tu vois\b", low):
        before, after = low[: m.start()], low[m.end() :]
        loose = m.start() == 0 or re.search(r"[,.?!…]\s*$", before) or re.match(r"\s*([,.!…]|$)", after)
        if loose and not re.match(r"\s*\?", after) and not TU_VOIS_OBJECT.match(after):
            add(m.start(), m.end(), "tu vois")
    for m in re.finditer(START + r"en gros\b", low):
        if not EN_GROS_TRADE.search(low[: m.start()]):
            add(m.start(), m.end(), "en gros")
    for m in re.finditer(START + r"quoi\b", low):
        before, after = low[: m.start()], low[m.end() :]
        if QUOI_KEEP_BEFORE.search(before) or not re.match(r"\s*([.!…]|$)", after):
            continue
        add(m.start(), m.end(), "quoi")
    for m in re.finditer(START + r"du coup\b", low):
        if not _keep_du_coup(low, m.start(), m.end()):
            add(m.start(), m.end(), "du coup")
    for m in re.finditer(START + r"genre\b", low):
        if not _keep_genre(low, m.start(), m.end()):
            add(m.start(), m.end(), "genre")
    for m in re.finditer(START + r"bah\b", low):
        add(m.start(), m.end(), "bah")
    return sorted(cuts)


def _ack(text):
    words = tokens(text)
    if not words or len(words) > MAX_ACK_TOKENS:
        return False
    rest = " ".join(words)
    for phrase in ACK_PHRASES:
        rest = re.sub(rf"(?<!\S){re.escape(phrase)}(?!\S)", " ", rest)
    return not rest.strip()


def repeat_cuts(text):
    cuts = []
    for m in REPEAT.finditer(text):
        unit = m.group(1)
        words = set(tokens(unit))
        if any(ch.isdigit() for ch in unit) or _quoted(text, m.start()):
            continue
        if words & NEGATIVE or words & KEEP_REPEATED or _ack(unit):
            continue
        cuts.append((m.start() + len(unit), m.end(), "repeat"))
    return cuts


def _join(left, right, removed):
    left = left.rstrip(" ")
    right = right.lstrip(" ")
    at_start = not left.strip() or left.rstrip()[-1] in STOPS
    if right.startswith(",") and (at_start or left.endswith(",")):
        right = right[1:].lstrip(" ")
    if left.endswith(",") and (not right or right[0] in STOPS):
        left = left[:-1]
    if at_start and right[:1].islower() and removed[:1].isupper():
        right = right[0].upper() + right[1:]
    if not left or not right or right[0] in ",.?!…":
        return left + right
    return left + " " + right


def cut(text, cuts):
    kept, last = [], -1
    for start, end, kind in sorted(cuts):
        if start >= last:
            kept.append((start, end, kind))
            last = end
    out = text
    for start, end, _ in reversed(kept):
        out = _join(out[:start], out[end:], out[start:end])
    return out, kept


def _ends_question(text):
    return text.rstrip().rstrip("»\"' ").endswith("?")


def _proposal(text):
    parts = [m.group() for m in SENTENCE.finditer(text) if m.group().strip()]
    return bool(PROPOSAL.search(norm(parts[-1] if parts else text)))


def _backchannel(turns, i):
    if i == 0 or i + 1 >= len(turns):
        return False
    before, line, after = turns[i - 1], turns[i], turns[i + 1]
    if before["who"] == line["who"] or after["who"] != before["who"]:
        return False
    if not line["joined"] or not after["joined"]:
        return False
    text = line["text"]
    if not _ack(text) or STRONG.search(norm(text)) or text.rstrip()[-1:] not in STOPS:
        return False
    if _ends_question(before["text"]) or _proposal(before["text"]):
        return False
    if norm(text).lstrip().startswith("d'accord") and before["text"].rstrip()[-1:] not in STOPS:
        return False
    return True


def _turns(lines):
    turns = []
    for n, raw in enumerate(lines):
        found = TURN.match(raw)
        if found:
            turns.append({"n": n, "prefix": found.group(1), "who": found.group(2), "text": found.group(3)})
    for k, turn in enumerate(turns):
        between = lines[turns[k - 1]["n"] + 1 : turn["n"]] if k else ["x"]
        turn["joined"] = not any(line.strip() for line in between)
    return turns


def clean(markdown):
    lines = markdown.split("\n")
    turns = _turns(lines)
    drop = set()
    entries = []
    for k, turn in enumerate(turns):
        n = turn["n"]
        if _backchannel(turns, k):
            drop.add(n)
            if n + 1 < len(lines) and not lines[n + 1].strip():
                drop.add(n + 1)
            entries.append({"type": "backchannel", "line": n + 1, "speaker": turn["who"], "text": turn["text"]})
            continue
        text = turn["text"]
        cuts = [(s, e, "filler") for s, e, _ in filler_cuts(text)]
        cuts += [c for c in repeat_cuts(text) if not _overlaps(cuts, c[0], c[1])]
        if not cuts:
            continue
        new, kept = cut(text, cuts)
        if not re.search(r"\w", new):
            continue
        lines[n] = turn["prefix"] + new
        for start, end, kind in kept:
            entries.append({"type": kind, "line": n + 1, "speaker": turn["who"], "text": text[start:end].strip()})
    out = [line for n, line in enumerate(lines) if n not in drop]
    return "\n".join(out), entries


def verbatim_path(path):
    path = Path(path)
    return path.with_name(f"{path.stem}.verbatim{path.suffix}")


def clean_file(path, log):
    path = Path(path)
    verbatim = verbatim_path(path)
    original = verbatim.read_text(encoding="utf-8") if verbatim.is_file() else path.read_text(encoding="utf-8")
    cleaned, entries = clean(original)
    if not verbatim.is_file():
        verbatim.write_text(original, encoding="utf-8")
    path.write_text(cleaned, encoding="utf-8")
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    record = {"transcript": str(path), "verbatim": str(verbatim), "cuts": entries}
    log.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return entries
