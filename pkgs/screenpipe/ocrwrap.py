#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

CFG = {
    "candidates": os.environ.get("OW_CANDIDATES", "6:1,6:2"),
    "small_text_height": int(os.environ.get("OW_SMALLTEXT", "0")),
    "small_scale": float(os.environ.get("OW_SMALLSCALE", "2")),
    "accept_conf": float(os.environ.get("OW_ACCEPT", "80")),
    "nice": int(os.environ.get("OW_NICE", "10")),
    "lang": os.environ.get("OW_LANG", ""),
    "workers": int(os.environ.get("OW_WORKERS", str(os.cpu_count() or 4))),
    "band_height": int(os.environ.get("OW_BAND", "80")),
    "pad": int(os.environ.get("OW_PAD", "6")),
    "edge_threshold": int(os.environ.get("OW_THRESH", "24")),
    "line_fraction": float(os.environ.get("OW_LINEFRAC", "0.5")),
    "min_row_ink": int(os.environ.get("OW_MINROW", "3")),
    "col_gap": int(os.environ.get("OW_COLGAP", "60")),
    "min_col_ink": int(os.environ.get("OW_MINCOL", "3")),
    "invert": os.environ.get("OW_INVERT", "auto"),
    "rule_length": int(os.environ.get("OW_RULE", "200")),
    "extra": os.environ.get("OW_EXTRA", ""),
}


def real_tesseract():
    env = os.environ.get("REAL_TESSERACT")
    if env:
        return env
    me = os.path.realpath(__file__)
    try:
        parent_exe = os.readlink(f"/proc/{os.getppid()}/exe")
        sibling = os.path.join(os.path.dirname(parent_exe), "tesseract")
        if os.access(sibling, os.X_OK) and os.path.realpath(sibling) != me:
            return sibling
    except OSError:
        pass
    for d in os.environ.get("PATH", "").split(":"):
        c = os.path.join(d, "tesseract")
        if os.access(c, os.X_OK) and os.path.realpath(c) != me:
            return c
    sys.exit("ocrwrap: real tesseract not found")


def passthrough(real):
    os.execv(real, [real] + sys.argv[1:])


def load_gray_and_edges(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    w, h = map(int, probe.stdout.strip().split(",")[:2])
    stacked = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-filter_complex",
         "[0]format=gray,split[g][e];[e]sobel[s];[g][s]vstack",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True).stdout
    return w, h, stacked[:w * h], stacked[w * h:]


def ink_mask(w, h, edges):
    t = CFG["edge_threshold"]
    mask = bytearray(edges.translate(bytes(0 if v <= t else 1 for v in range(256))))
    blank_col = bytes(h)
    for x in range(w):
        if mask[x::w].count(1) > h * CFG["line_fraction"]:
            mask[x::w] = blank_col
    return bytes(mask)


def runs_of(flags, min_gap):
    runs, start, end, gap = [], None, 0, 0
    for i, on in enumerate(flags):
        if on:
            if start is None:
                start = i
            gap = 0
            end = i + 1
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                runs.append((start, end))
                start = None
    if start is not None:
        runs.append((start, end))
    return runs


def column_counts(w, mask, x0, y0, x1, y1):
    return [mask[y0 * w + x:y1 * w:w].count(1) for x in range(x0, x1)]


def row_counts(w, mask, x0, y0, x1, y1):
    return [mask[y * w + x0:y * w + x1].count(1) for y in range(y0, y1)]


def split_columns(w, mask, region):
    x0, y0, x1, y1 = region
    height = y1 - y0
    counts = column_counts(w, mask, x0, y0, x1, y1)
    solid = height * CFG["line_fraction"] if height > 40 else height + 1
    blank = bytes(height)
    for i, c in enumerate(counts):
        if c >= solid:
            mask[y0 * w + x0 + i:y1 * w:w] = blank
    inked = [CFG["min_col_ink"] <= c < solid for c in counts]
    return [(x0 + s, y0, x0 + e, y1) for s, e in runs_of(inked, CFG["col_gap"])]


def force_rows(w, mask, region):
    x0, y0, x1, y1 = region
    counts = row_counts(w, mask, x0, y0, x1, y1)
    target, cuts, start = CFG["band_height"], [], 0
    while len(counts) - start > target:
        window = range(start + target // 2, start + target)
        cut = min(window, key=lambda i: counts[i])
        cuts.append((x0, y0 + start, x1, y0 + cut))
        start = cut
    cuts.append((x0, y0 + start, x1, y1))
    return cuts


def text_line_height(w, mask, box):
    counts = row_counts(w, mask, *box)
    heights = sorted(e - s for s, e in runs_of([c >= CFG["min_row_ink"] for c in counts], 1))
    return heights[len(heights) // 2] if heights else 0


def split_rows(w, mask, region):
    x0, y0, x1, y1 = region
    counts = row_counts(w, mask, x0, y0, x1, y1)
    solid = (x1 - x0) * 0.9
    inked = [CFG["min_row_ink"] <= c < solid for c in counts]
    lines = runs_of(inked, 1)
    if not lines:
        return []
    groups = [list(lines[0])]
    for s, e in lines[1:]:
        if e - groups[-1][0] <= CFG["band_height"]:
            groups[-1][1] = e
        else:
            groups.append([s, e])
    return [(x0, y0 + s, x1, y0 + e) for s, e in groups]


def xy_cut(w, mask, region, depth=0):
    columns = split_columns(w, mask, region)
    if depth > 12:
        return columns
    boxes = []
    for col in columns:
        rows = split_rows(w, mask, col)
        if len(rows) == 1 and rows[0] == col:
            if col[3] - col[1] > CFG["band_height"]:
                for chunk in force_rows(w, mask, col):
                    boxes.extend(split_columns(w, mask, chunk))
            else:
                boxes.append(col)
            continue
        for row in rows:
            if row[3] - row[1] <= CFG["band_height"]:
                boxes.extend(split_columns(w, mask, row) or [])
            else:
                boxes.extend(xy_cut(w, mask, row, depth + 1))
    return boxes


def find_boxes(w, h, mask):
    pad = CFG["pad"]
    mask = bytearray(mask)
    return [(max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
            for x0, y0, x1, y1 in xy_cut(w, mask, (0, 0, w, h))]


def erase_horizontal_rules(w, h, raw, mask):
    rule = re.compile(rb"(.)\1{%d,}" % (CFG["rule_length"] - 1), re.DOTALL)
    t = CFG["edge_threshold"]
    out, cleared = bytearray(raw), bytearray(mask)
    for y in range(2, h - 2):
        if mask[y * w:(y + 1) * w].count(1) < min(CFG["rule_length"], w // 4):
            continue
        row = raw[y * w:(y + 1) * w]
        for m in rule.finditer(row):
            s, e = m.start(), m.end()
            mid = (s + e) // 2
            above, below = raw[(y - 2) * w + mid], raw[(y + 2) * w + mid]
            line = m.group(1)[0]
            if abs(line - above) > t and abs(line - below) > t:
                out[y * w + s:y * w + e] = bytes([above]) * (e - s)
                for yy in range(y - 1, y + 2):
                    cleared[yy * w + s:yy * w + e] = bytes(e - s)
    return bytes(out), bytes(cleared)


INVERT_TABLE = bytes(range(255, -1, -1))


def crop(w, raw, box):
    x0, y0, x1, y1 = box
    return b"".join(raw[y * w + x0:y * w + x1] for y in range(y0, y1))


def is_dark_background(w, raw, box):
    if CFG["invert"] in ("0", "1"):
        return CFG["invert"] == "1"
    sample = crop(w, raw, box)[::7]
    return max(set(sample), key=sample.count) < 128


def write_pgm(path, w, raw, box, invert):
    data = crop(w, raw, box)
    if invert == "auto":
        invert = is_dark_background(w, raw, box)
    if invert:
        data = data.translate(INVERT_TABLE)
    with open(path, "wb") as f:
        f.write(b"P5\n%d %d\n255\n" % (box[2] - box[0], box[3] - box[1]))
        f.write(data)


def scale_gray(w, h, raw, scale):
    if scale == 1:
        return w, raw
    sw, sh = round(w * scale), round(h * scale)
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
         "-i", "-", "-vf", f"scale={sw}:{sh}:flags=lanczos",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        input=raw, capture_output=True, check=True).stdout
    return sw, out


def scaled_box(box, scale, sw):
    x0, y0, x1, y1 = box
    return (round(x0 * scale), round(y0 * scale), min(sw, round(x1 * scale)), round(y1 * scale))


def balanced_chunks(boxes, count):
    bins = [[] for _ in range(max(1, min(count, len(boxes))))]
    load = [0] * len(bins)
    order = sorted(range(len(boxes)), key=lambda i: -(boxes[i][2] - boxes[i][0]) * (boxes[i][3] - boxes[i][1]))
    for i in order:
        target = load.index(min(load))
        bins[target].append(i)
        x0, y0, x1, y1 = boxes[i]
        load[target] += (x1 - x0) * (y1 - y0)
    return [b for b in bins if b]


def ocr_batch(real, image_paths, list_path, psm):
    with open(list_path, "w") as f:
        f.write("\n".join(image_paths) + "\n")
    args = [real, list_path, "stdout", "-l", CFG["lang"], "--psm", psm, "--oem", "1",
            "--dpi", "300", "-c", "tessedit_create_tsv=1"]
    if CFG["extra"]:
        args += CFG["extra"].split()
    args.append("tsv")
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    tsv = subprocess.run(args, capture_output=True, text=True, env=env).stdout
    pages = [[] for _ in image_paths]
    for ln in tsv.splitlines():
        p = ln.split("\t")
        if len(p) >= 12 and p[1].isdigit() and 1 <= int(p[1]) <= len(pages):
            pages[int(p[1]) - 1].append(ln)
    return ["header\n" + "\n".join(lines) for lines in pages]


def tsv_quality(tsv):
    total = 0.0
    for ln in tsv.splitlines()[1:]:
        p = ln.split("\t")
        if len(p) >= 12 and p[0] == "5" and p[11].strip():
            total += max(float(p[10]), 0) * sum(c.isalnum() for c in p[11])
    return total


def mean_confidence(tsv):
    confs = []
    for ln in tsv.splitlines()[1:]:
        p = ln.split("\t")
        if len(p) >= 12 and p[0] == "5" and p[11].strip():
            confs.append(float(p[10]))
    return sum(confs) / len(confs) if confs else 0.0


def candidates():
    return [(psm, float(scale)) for psm, scale in
            (c.split(":") for c in CFG["candidates"].split(","))]


def merge_tsv(w, h, boxes, outs, scales):
    lines = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
             f"1\t1\t0\t0\t0\t0\t0\t0\t{w}\t{h}\t-1\t"]
    block_base = 0
    for (x0, y0, _, _), out, scale in zip(boxes, outs, scales):
        max_block = 0
        for ln in out.splitlines()[1:]:
            p = ln.split("\t")
            if len(p) < 12 or p[0] == "1":
                continue
            block = int(p[2])
            max_block = max(max_block, block)
            p[2] = str(block + block_base)
            p[6] = str(round(int(p[6]) / scale) + x0)
            p[7] = str(round(int(p[7]) / scale) + y0)
            p[8] = str(round(int(p[8]) / scale))
            p[9] = str(round(int(p[9]) / scale))
            lines.append("\t".join(p[:12]))
        block_base += max_block
    return "\n".join(lines) + "\n"


STAGE_START = [time.time()]


def stage(name):
    if os.environ.get("OW_PROFILE"):
        now = time.time()
        print(f"ocrwrap: {name} {int((now - STAGE_START[0]) * 1000)}ms", file=sys.stderr)
        STAGE_START[0] = now


def run(real, image):
    stage("start")
    w, h, raw, edges = load_gray_and_edges(image)
    stage("load")
    mask = ink_mask(w, h, edges)
    if CFG["rule_length"] > 0:
        raw, mask = erase_horizontal_rules(w, h, raw, mask)
    stage("mask+rules")
    boxes = find_boxes(w, h, mask)
    stage(f"boxes={len(boxes)}")
    if not boxes:
        return merge_tsv(w, h, [], [], [])
    invert = [is_dark_background(w, raw, box) for box in boxes]
    options = candidates()
    small_text = [0 < text_line_height(w, mask, box) <= CFG["small_text_height"] for box in boxes]
    scales_needed = {s for _, s in options} | ({CFG["small_scale"]} if any(small_text) else set())
    with ThreadPoolExecutor(len(scales_needed)) as ex:
        scaled = dict(zip(scales_needed, ex.map(lambda s: scale_gray(w, h, raw, s), scales_needed)))
    stage("scale")
    tried = [[] for _ in boxes]
    pending = list(range(len(boxes)))
    with tempfile.TemporaryDirectory(prefix="ocrwrap-") as td:
        for k, (psm, scale) in enumerate(options):
            if not pending:
                break
            box_scale = {i: max(scale, CFG["small_scale"]) if small_text[i] else scale for i in pending}
            subset = [tuple(round(v * box_scale[i]) for v in boxes[i]) for i in pending]
            jobs = []
            for c, chunk in enumerate(balanced_chunks(subset, CFG["workers"])):
                ids = [pending[j] for j in chunk]
                paths = []
                for i in ids:
                    sw, sraw = scaled[box_scale[i]]
                    p = os.path.join(td, f"c{k}_{i}.pgm")
                    write_pgm(p, sw, sraw, scaled_box(boxes[i], box_scale[i], sw), invert[i])
                    paths.append(p)
                jobs.append((ids, paths, os.path.join(td, f"list{k}_{c}.txt")))
            with ThreadPoolExecutor(len(jobs)) as ex:
                batches = list(ex.map(lambda j: ocr_batch(real, j[1], j[2], psm), jobs))
            for (ids, _, _), pages in zip(jobs, batches):
                for i, tsv in zip(ids, pages):
                    tried[i].append((tsv_quality(tsv), tsv, box_scale[i]))
            pending = [i for i in pending if mean_confidence(tried[i][-1][1]) < CFG["accept_conf"]]
            stage(f"ocr psm={psm} scale={scale} boxes={len(subset)} retry={len(pending)}")
    outs, scales = [], []
    for attempts in tried:
        _, tsv, scale = max(attempts, key=lambda a: a[0])
        outs.append(tsv)
        scales.append(scale)
    return merge_tsv(w, h, boxes, outs, scales)


def main():
    real = real_tesseract()
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0].startswith("-") or argv[1] != "stdout" or "tsv" not in argv:
        passthrough(real)
    if not CFG["lang"]:
        CFG["lang"] = argv[argv.index("-l") + 1] if "-l" in argv[:-1] else "eng"
    if CFG["nice"]:
        os.nice(CFG["nice"])
    try:
        out = run(real, argv[0])
    except Exception as e:
        print(f"ocrwrap: fallback ({e})", file=sys.stderr)
        passthrough(real)
    sys.stdout.write(out)


if __name__ == "__main__":
    main()
