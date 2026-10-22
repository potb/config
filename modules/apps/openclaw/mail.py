#!/usr/bin/env python3
import argparse
import html.parser
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path
from xml.etree import ElementTree

GOG = os.environ.get("MAIL_GOG", "gog")
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/var/lib/openclaw/workspace"))
DOWNLOADS = Path(os.environ.get("MAIL_DOWNLOAD_DIR", WORKSPACE / "mail"))
STATE = Path(os.environ.get("MAIL_STATE", "/var/lib/openclaw/mail-state.json"))
KEEP_DAYS = 30
TEXT_LIMIT = 15000
OCR_PAGES = 10
OCR_LANGS = "fra+eng"
SMALL_IMAGE = 15 * 1024
NEW_QUERY = "in:inbox -category:promotions -category:social newer_than:3d"
HELP = """exemples :
  mail search                                   les 10 derniers emails de la boîte de réception
  mail search 'from:sncf newer_than:30d'        recherche Gmail, même syntaxe que dans Gmail
  mail search 'has:attachment facture' --max 20
  mail read <id>                                le fil complet, pièces jointes téléchargées et lues
  mail read --message <id>                      seulement ce message, pièces jointes comprises

Les ids viennent de mail search. mail read est la seule façon de lire un email :
le texte de chaque pièce jointe (PDF, scan, photo, Word, Excel...) est inclus."""
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".pnm"}
TEXT_EXT = {".txt", ".csv", ".tsv", ".ics", ".vcs", ".vcf", ".json", ".xml", ".md", ".log"}
HTML_EXT = {".html", ".htm"}
GOG_MARKER = re.compile(
    r'<<<EXTERNAL_UNTRUSTED_CONTENT id="[0-9a-f]+">>>\nSource: [^\n]*\n---\n(.*?)\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="[0-9a-f]+">>>',
    re.S,
)


class Failure(Exception):
    pass


def gog(*args):
    proc = subprocess.run([GOG, *args, "--json"], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise Failure((proc.stderr or proc.stdout).strip() or f"gog exited {proc.returncode}")
    return json.loads(proc.stdout)


def wrap(text, source):
    marker = secrets.token_hex(8)
    text = re.sub(r"<<<(END_)?EXTERNAL_UNTRUSTED_CONTENT", "<<<\\1EXTERNAL_UNTRUSTED_CONTENT_QUOTED", text)
    return (
        f'<<<EXTERNAL_UNTRUSTED_CONTENT id="{marker}">>>\nSource: {source}\n---\n'
        f'{text}\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="{marker}">>>'
    )


def plain(value):
    return GOG_MARKER.sub(lambda m: m.group(1), value or "")


def run_tool(args, timeout=120):
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    proc = subprocess.run(args, capture_output=True, timeout=timeout, env=env)
    if proc.returncode != 0:
        raise Failure(proc.stderr.decode("utf-8", "replace").strip()[:300] or f"{args[0]} exited {proc.returncode}")
    return proc.stdout.decode("utf-8", "replace")


def decode(data):
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def sniff(path):
    head = path.read_bytes()[:16] if path.stat().st_size else b""
    suffix = path.suffix.lower()
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return "unknown"
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        if any(n.startswith("ppt/slides/") for n in names):
            return "pptx"
        if "content.xml" in names:
            return "odf"
        return "zip"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8") or head.startswith(b"GIF8"):
        return "image"
    if head[:4] in (b"II*\x00", b"MM\x00*") or (head.startswith(b"RIFF") and head[8:12] == b"WEBP"):
        return "image"
    if suffix in {".heic", ".heif"}:
        return "heic"
    if suffix in IMAGE_EXT:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in HTML_EXT:
        return "html"
    if suffix == ".eml":
        return "eml"
    if suffix in TEXT_EXT:
        return "text"
    if suffix in {".doc", ".xls", ".ppt", ".rtf"}:
        return "legacy-office"
    return "unknown"


def ocr_image(path):
    return run_tool(["tesseract", str(path), "stdout", "-l", OCR_LANGS], timeout=180)


def extract_pdf(path):
    text = run_tool(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"])
    if len(re.sub(r"\s+", "", text)) >= 200:
        return text, "pdftotext"
    with tempfile.TemporaryDirectory() as tmp:
        run_tool(["pdftoppm", "-r", "200", "-gray", "-png", "-l", str(OCR_PAGES), str(path), f"{tmp}/page"], timeout=300)
        pages = sorted(Path(tmp).glob("page*.png"))
        parts = [f"[page {i}]\n{ocr_image(page).strip()}" for i, page in enumerate(pages, 1)]
    info = run_tool(["pdfinfo", str(path)])
    total = re.search(r"^Pages:\s+(\d+)", info, re.M)
    method = f"OCR tesseract {OCR_LANGS}"
    if total and int(total.group(1)) > OCR_PAGES:
        method += f", {OCR_PAGES} premières pages sur {total.group(1)}"
    return "\n\n".join(parts), method


def xml_text(root, paragraph_tags, text_tags, break_tags=()):
    lines = []
    for paragraph in root.iter():
        if paragraph.tag not in paragraph_tags:
            continue
        chunk = []
        for node in paragraph.iter():
            if node.tag in text_tags and node.text:
                chunk.append(node.text)
            elif node.tag in break_tags:
                chunk.append("\t" if node.tag.endswith("}tab") else "\n")
        line = "".join(chunk).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE_NS = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"


def extract_docx(path):
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(W + "body")
    lines = []
    for node in body if body is not None else []:
        if node.tag == W + "tbl":
            for row in node.iter(W + "tr"):
                cells = [xml_text(cell, {W + "p"}, {W + "t"}, {W + "tab", W + "br"}).replace("\n", " ") for cell in row.iter(W + "tc")]
                line = "\t".join(cells).rstrip()
                if line:
                    lines.append(line)
        else:
            text = xml_text(node, {W + "p"}, {W + "t"}, {W + "tab", W + "br"})
            if text:
                lines.append(text)
    return "\n".join(lines)


def extract_pptx(path):
    with zipfile.ZipFile(path) as archive:
        slides = sorted(
            (n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)", n).group(1)),
        )
        parts = []
        for i, name in enumerate(slides, 1):
            root = ElementTree.fromstring(archive.read(name))
            parts.append(f"[diapositive {i}]\n" + xml_text(root, {A + "p"}, {A + "t"}))
    return "\n\n".join(parts)


def column_index(ref):
    letters = re.match(r"[A-Z]+", ref or "")
    if not letters:
        return 0
    index = 0
    for ch in letters.group(0):
        index = index * 26 + ord(ch) - 64
    return index - 1


def extract_xlsx(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(S + "t")) for si in root.iter(S + "si")]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels")):
                rels[rel.get("Id")] = rel.get("Target", "").lstrip("/").removeprefix("xl/")
        parts = []
        for sheet in workbook.iter(S + "sheet"):
            target = rels.get(sheet.get(R + "id"), "")
            member = f"xl/{target}"
            if member not in names:
                continue
            rows = []
            for row in ElementTree.fromstring(archive.read(member)).iter(S + "row"):
                cells = {}
                for cell in row.iter(S + "c"):
                    kind = cell.get("t")
                    value = cell.find(S + "v")
                    if kind == "inlineStr":
                        text = "".join(t.text or "" for t in cell.iter(S + "t"))
                    elif value is None:
                        continue
                    elif kind == "s":
                        text = shared[int(value.text)] if value.text and int(value.text) < len(shared) else ""
                    else:
                        text = value.text or ""
                    cells[column_index(cell.get("r"))] = text
                if cells:
                    rows.append("\t".join(cells.get(i, "") for i in range(max(cells) + 1)).rstrip())
            parts.append(f"[feuille {sheet.get('name')}]\n" + "\n".join(rows))
    return "\n\n".join(parts)


def extract_odf(path):
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("content.xml"))
    rows = list(root.iter(TABLE_NS + "table-row"))
    if rows and not list(root.iter(TEXT_NS + "h")):
        lines = []
        for row in rows:
            cells = ["".join(cell.itertext()).strip() for cell in row.iter(TABLE_NS + "table-cell")]
            line = "\t".join(cells).rstrip()
            if line:
                lines.append(line)
        return "\n".join(lines)
    lines = ["".join(node.itertext()).strip() for node in root.iter() if node.tag in (TEXT_NS + "p", TEXT_NS + "h")]
    return "\n".join(line for line in lines if line)


class TextOnly(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract_html(path):
    parser = TextOnly()
    parser.feed(decode(path.read_bytes()))
    return re.sub(r"\n\s*\n+", "\n\n", "".join(parser.parts)).strip()


def extract_eml(path):
    message = BytesParser(policy=policy.default).parse(path.open("rb"))
    head = "\n".join(f"{k} : {message.get(k, '')}" for k in ("From", "To", "Date", "Subject"))
    body = message.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    names = [part.get_filename() for part in message.iter_attachments() if part.get_filename()]
    tail = f"\n\nPièces jointes du message joint : {', '.join(names)}" if names else ""
    return f"{head}\n\n{text}{tail}"


def extract(path, size):
    kind = sniff(path)
    if kind == "pdf":
        return extract_pdf(path)
    if kind == "image":
        if size < SMALL_IMAGE:
            return "", "ignorée : petite image (logo ou signature probable)"
        return ocr_image(path), f"OCR tesseract {OCR_LANGS}"
    if kind == "docx":
        return extract_docx(path), "docx"
    if kind == "xlsx":
        return extract_xlsx(path), "xlsx"
    if kind == "pptx":
        return extract_pptx(path), "pptx"
    if kind == "odf":
        return extract_odf(path), "OpenDocument"
    if kind == "html":
        return extract_html(path), "html"
    if kind == "eml":
        return extract_eml(path), "email joint"
    if kind == "text":
        return decode(path.read_bytes()), "texte"
    if kind == "zip":
        with zipfile.ZipFile(path) as archive:
            return "\n".join(archive.namelist()), "archive zip, liste des fichiers seulement"
    if kind == "heic":
        return "", "non lue : HEIC non pris en charge, ouvre le fichier avec view_image"
    if kind == "legacy-office":
        return "", "non lue : ancien format Office non pris en charge"
    return "", "non lue : format non reconnu"


def attachment_block(att, path, index, total):
    size = att.get("size") or (path.stat().st_size if path else 0)
    head = f"--- Pièce jointe {index}/{total} : {att.get('filename') or '(sans nom)'} ({att.get('mimeType', '?')}, {att.get('sizeHuman') or size})"
    if path is None or not path.exists():
        return f"{head}\nNon téléchargée."
    lines = [head, f"Fichier : {path}"]
    try:
        text, method = extract(path, size)
    except (Failure, subprocess.TimeoutExpired, zipfile.BadZipFile, ElementTree.ParseError, KeyError, ValueError) as err:
        lines.append(f"Extraction échouée : {str(err)[:300]}")
        return "\n".join(lines)
    text = text.strip()
    lines.append(f"Extraction : {method}")
    if not text:
        if not method.startswith(("ignorée", "non lue")):
            lines.append("Aucun texte trouvé. Ouvre le fichier avec view_image ou pdf.")
        return "\n".join(lines)
    full = path.with_name(path.name + ".txt")
    full.write_text(text)
    if len(text) > TEXT_LIMIT:
        lines.append(f"Texte tronqué à {TEXT_LIMIT} caractères sur {len(text)}. Texte complet : {full}")
        text = text[:TEXT_LIMIT]
    lines.append(wrap(text, "gmail_attachment"))
    return "\n".join(lines)


def find_key(data, key):
    if isinstance(data, dict):
        if isinstance(data.get(key), str):
            return data[key]
        for value in data.values():
            found = find_key(value, key)
            if found:
                return found
    if isinstance(data, list):
        for value in data:
            found = find_key(value, key)
            if found:
                return found
    return None


def fetch_thread(ident, out_dir):
    args = ("--full", "--sanitize-content", "--download", "--out-dir", str(out_dir))
    try:
        return gog("gmail", "thread", "get", ident, *args)
    except Failure as err:
        if "404" not in str(err) and "not found" not in str(err).lower():
            raise
    thread_id = find_key(gog("gmail", "get", ident, "--format", "metadata"), "threadId")
    if not thread_id:
        raise Failure(f"message ou fil introuvable : {ident}")
    return gog("gmail", "thread", "get", thread_id, *args)


def prune():
    if not DOWNLOADS.is_dir():
        return
    cutoff = time.time() - KEEP_DAYS * 86400
    for entry in DOWNLOADS.iterdir():
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry, ignore_errors=True)


def read_one(ident, only_message):
    staging = DOWNLOADS / f".{ident}"
    staging.mkdir(parents=True, exist_ok=True)
    data = fetch_thread(ident, staging)
    thread = data.get("thread") or {}
    thread_id = thread.get("id") or ident
    out_dir = DOWNLOADS / thread_id
    if staging != out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in staging.iterdir():
            item.replace(out_dir / item.name)
        staging.rmdir()
    os.utime(out_dir)
    downloaded = {}
    for item in data.get("downloaded") or []:
        path = out_dir / Path(item.get("path", "")).name
        downloaded[(item.get("messageId"), item.get("attachmentId"))] = path
        downloaded.setdefault((item.get("messageId"), item.get("filename")), path)
    messages = thread.get("messages") or []
    if only_message:
        messages = [m for m in messages if m.get("id") == ident] or messages
    blocks = [f"Fil {thread_id} : {len(thread.get('messages') or [])} message(s)"]
    for n, msg in enumerate(messages, 1):
        headers = msg.get("headers") or {}
        attachments = msg.get("attachments") or []
        content = [
            f"Date : {plain(headers.get('date'))}",
            f"De : {plain(headers.get('from'))}",
            f"À : {plain(headers.get('to'))}",
        ]
        if headers.get("cc"):
            content.append(f"Cc : {plain(headers['cc'])}")
        content += [f"Objet : {plain(headers.get('subject'))}", "", plain(msg.get("body")) or "(corps vide)"]
        block = [
            f"=== Message {n}/{len(messages)} : {msg.get('id')}",
            f"Libellés : {', '.join(msg.get('labelIds') or [])}",
            f"Pièces jointes : {len(attachments)}",
            wrap("\n".join(content), "gmail"),
        ]
        for i, att in enumerate(attachments, 1):
            path = downloaded.get((msg.get("id"), att.get("attachmentId"))) or downloaded.get((msg.get("id"), att.get("filename")))
            block += ["", attachment_block(att, path, i, len(attachments))]
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def cmd_read(args):
    prune()
    outputs = []
    for ident in args.ids:
        try:
            outputs.append(read_one(ident, args.message))
        except (Failure, subprocess.TimeoutExpired) as err:
            outputs.append(f"Fil {ident} : lecture impossible : {err}")
    print("\n\n".join(outputs))


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"handled": {}, "listed": []}


def save_state(state):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE)


def summarize(messages):
    rows = []
    for msg in messages:
        rows.append(
            {
                "id": msg.get("id"),
                "threadId": msg.get("threadId"),
                "date": msg.get("internalDateIso") or msg.get("date"),
                "from": plain(msg.get("from")),
                "subject": plain(msg.get("subject")),
                "attachments": [plain(a.get("filename")) for a in msg.get("attachments") or []],
            }
        )
    return rows


def listing(rows):
    lines = []
    for m in rows:
        extra = f" [{len(m['attachments'])} PJ : {', '.join(m['attachments'])}]" if m["attachments"] else ""
        lines.append(f"{m['id']}\t{m['date']}\t{m['from']}\t{m['subject']}{extra}")
    return wrap("\n".join(lines), "gmail") if lines else ""


def cmd_search(args):
    data = gog("gmail", "messages", "search", args.query, "--max", str(args.max), "--include-attachments")
    rows = summarize(data.get("messages") or [])
    if not rows:
        print("Aucun email ne correspond.")
        return
    print("id\tdate\tde\tobjet [pièces jointes]\n" + listing(rows) + "\n\nPour lire un email et ses pièces jointes : mail read <id>")


def cmd_new(args):
    state = load_state()
    cutoff = time.time() - 7 * 86400
    state["handled"] = {k: v for k, v in state.get("handled", {}).items() if v > cutoff}
    data = gog("gmail", "messages", "search", NEW_QUERY, "--max", "50", "--include-attachments")
    fresh = [m for m in summarize(data.get("messages") or []) if m["id"] not in state["handled"]]
    fresh.sort(key=lambda m: m["date"] or "")
    state["listed"] = [m["id"] for m in fresh]
    save_state(state)
    text = listing(fresh)
    if args.json:
        print(json.dumps({"count": len(fresh), "ids": [m["id"] for m in fresh], "text": text}, ensure_ascii=False))
    elif text:
        print(text)


def cmd_ack(args):
    state = load_state()
    ids = args.ids or state.get("listed", [])
    now = time.time()
    for ident in ids:
        state.setdefault("handled", {})[ident] = now
    state["listed"] = [i for i in state.get("listed", []) if i not in ids]
    save_state(state)
    print(f"{len(ids)} message(s) marqué(s) comme traité(s)")


def main():
    parser = argparse.ArgumentParser(
        prog="mail",
        description="Gmail de Peïo, en lecture seule : chercher et lire les emails, pièces jointes comprises.",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="Chercher des emails (syntaxe Gmail), du plus récent au plus ancien")
    search.add_argument("query", nargs="?", default="in:inbox", help="Requête Gmail, par défaut in:inbox")
    search.add_argument("--max", type=int, default=10)
    search.set_defaults(func=cmd_search)
    read = sub.add_parser("read", help="Lire un fil ou un message, pièces jointes comprises")
    read.add_argument("ids", nargs="+", help="Identifiant de message ou de fil")
    read.add_argument("--message", action="store_true", help="Seulement le message donné, pas tout le fil")
    read.set_defaults(func=cmd_read)
    new = sub.add_parser("new", help="Messages récents pas encore traités")
    new.add_argument("--json", action="store_true")
    new.set_defaults(func=cmd_new)
    ack = sub.add_parser("ack", help="Marquer des messages comme traités (par défaut ceux du dernier mail new)")
    ack.add_argument("ids", nargs="*")
    ack.set_defaults(func=cmd_ack)
    args = parser.parse_args()
    try:
        args.func(args)
    except (Failure, subprocess.TimeoutExpired) as err:
        print(f"mail : {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
