import json
import logging
import os
import subprocess
import time
from bisect import bisect_right
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import chunks, state
from . import voices as voices_module

LOG = logging.getLogger(__name__)

SAMPLE_RATE = 16000
VAD_FRAME = 512
VAD_CONTEXT = 64
VAD_THRESHOLD = 0.5
MIN_SPEECH_REGION = 0.25
MIN_REGION_GAP = 0.35
REGION_PAD = 0.1
WINDOW = 1.5
HOP = 0.75
MIN_WINDOW = 0.6
GAP_SECONDS = 1.5
MIN_SPEECH_SECONDS = 120.0
MAX_SPEAKERS = 6
MAX_CLUSTER_WINDOWS = 6000
STEP = 0.05
MEDIAN_FRAMES = 9
MERGE_GAP = 0.5
MIN_TURN = 0.3
NEAR_TURN = 1.0
ISLAND_WORDS = 2
KEEP_TURN = 1.0
SNAP_WINDOW = 0.5
SENTENCE_END = ".?!\u2026"
CLAUSE_END = ",;:"
DIALOGUE_DASHES = ("\u2014", "\u2013", "-")
TIMEOUT = 3600
SPEAKERS_JSON = "speakers.json"
SPEAKERS_NPZ = "speakers.npz"
OTHERS = "others"

Piece = namedtuple("Piece", "name start offset seconds")


class DiarizationError(RuntimeError):
    pass


class TooLittleSpeech(DiarizationError):
    pass


def available(cfg):
    if not cfg.diarization:
        return False
    return all(path is not None and Path(path).is_file() for path in (cfg.speaker_model, cfg.speech_vad_model))


def unavailable_reason(cfg):
    if not cfg.diarization:
        return "disabled"
    missing = [
        label
        for label, path in (("speaker model", cfg.speaker_model), ("vad model", cfg.speech_vad_model))
        if path is None or not Path(path).is_file()
    ]
    return "missing " + " and ".join(missing)


def others_chunks(audio_dir, start, end, floor=None):
    found = []
    for path in chunks.meeting_chunks(audio_dir, start, end, floor=floor):
        parsed = chunks.parse(path.name)
        if parsed and parsed[1] == OTHERS:
            found.append((parsed[2], path))
    return found


def decode_chunk(cfg, path, run=subprocess.run):
    import numpy as np

    argv = [
        cfg.ffmpeg, "-nostdin", "-v", "error", "-i", str(path),
        "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
    ]
    result = run(argv, capture_output=True, check=False)
    if result.returncode != 0 or not result.stdout:
        return None
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    return samples if samples.size else None


def assemble(items, decode, gap=GAP_SECONDS):
    import numpy as np

    parts = []
    pieces = []
    skipped = []
    cursor = 0
    previous_end = None
    for t0, path in sorted(items, key=lambda item: item[0]):
        samples = decode(path)
        if samples is None:
            LOG.warning("diarization skips unreadable chunk %s", Path(path).name)
            skipped.append(Path(path).name)
            continue
        if previous_end is not None:
            silence = (t0 - previous_end).total_seconds()
            if silence > gap:
                count = int(round(silence * SAMPLE_RATE))
                parts.append(np.zeros(count, dtype=np.float32))
                cursor += count
        seconds = samples.size / SAMPLE_RATE
        pieces.append(Piece(Path(path).name, t0, cursor / SAMPLE_RATE, seconds))
        parts.append(samples.astype(np.float32, copy=False))
        cursor += samples.size
        previous_end = t0 + timedelta(seconds=seconds)
    audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return audio, pieces, skipped


def speech_regions(probs, total, threshold=VAD_THRESHOLD):
    frame = VAD_FRAME / SAMPLE_RATE
    raw = []
    start = None
    for index, prob in enumerate(probs):
        if prob > threshold and start is None:
            start = index
        elif prob <= threshold and start is not None:
            raw.append([start * frame, index * frame])
            start = None
    if start is not None:
        raw.append([start * frame, len(probs) * frame])
    merged = []
    for region in raw:
        if merged and region[0] - merged[-1][1] < MIN_REGION_GAP:
            merged[-1][1] = region[1]
        else:
            merged.append(region)
    return [
        (max(0.0, begin - REGION_PAD), min(total, end + REGION_PAD))
        for begin, end in merged
        if end - begin >= MIN_SPEECH_REGION
    ]


def windows(regions, size=WINDOW, hop=HOP):
    found = []
    for begin, end in regions:
        if end - begin <= size * 1.2:
            found.append((begin, end))
            continue
        cursor = begin
        while cursor + size <= end + 1e-6:
            found.append((cursor, cursor + size))
            cursor += hop
        if found[-1][1] < end - 0.3:
            found.append((end - size, end))
    return [(begin, end) for begin, end in found if end - begin >= MIN_WINDOW]


def _normalise(matrix):
    import numpy as np

    return matrix / (np.linalg.norm(matrix, axis=-1, keepdims=True) + 1e-9)


def kmeans(points, k, seed=0, restarts=20, iterations=300):
    import numpy as np

    rng = np.random.default_rng(seed)
    count = len(points)
    best_labels, best_inertia = None, None
    for _ in range(restarts):
        centers = [points[rng.integers(count)]]
        for _ in range(1, k):
            distance = np.min(((points[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
            total = distance.sum()
            pick = rng.choice(count, p=distance / total) if total > 0 else rng.integers(count)
            centers.append(points[pick])
        centers = np.array(centers)
        for _ in range(iterations):
            distance = ((points[:, None, :] - centers[None]) ** 2).sum(-1)
            labels = distance.argmin(1)
            moved = np.array([
                points[labels == j].mean(0) if np.any(labels == j) else centers[j] for j in range(k)
            ])
            if np.allclose(moved, centers):
                break
            centers = moved
        distance = ((points[:, None, :] - centers[None]) ** 2).sum(-1)
        labels = distance.argmin(1)
        inertia = float(distance[np.arange(count), labels].sum())
        if best_inertia is None or inertia < best_inertia - 1e-9:
            best_labels, best_inertia = labels, inertia
    return best_labels


def spectral(embeddings, max_speakers=MAX_SPEAKERS):
    import numpy as np

    count = len(embeddings)
    if count <= max_speakers + 1:
        raise DiarizationError(f"only {count} speech windows")
    affinity = (np.clip(embeddings @ embeddings.T, -1, 1) + 1) / 2
    neighbours = max(5, int(0.1 * count))
    sparse = np.zeros_like(affinity)
    nearest = np.argsort(-affinity, 1)[:, :neighbours]
    rows = np.arange(count)[:, None]
    sparse[rows, nearest] = affinity[rows, nearest]
    sparse = np.maximum(sparse, sparse.T)
    np.fill_diagonal(sparse, 0)
    degree = sparse.sum(1) + 1e-9
    laplacian = np.eye(count) - sparse / np.sqrt(np.outer(degree, degree))
    values, vectors = np.linalg.eigh(laplacian)
    gaps = np.diff(values[: max_speakers + 1])
    k = int(np.argmax(gaps) + 1)
    if k == 1:
        return np.zeros(count, dtype=int), 1, values[: max_speakers + 1]
    spectrum = _normalise(vectors[:, :k])
    return kmeans(spectrum, k), k, values[: max_speakers + 1]


def cluster(embeddings, max_speakers=MAX_SPEAKERS, limit=MAX_CLUSTER_WINDOWS):
    import numpy as np

    count = len(embeddings)
    if count <= limit:
        labels, k, values = spectral(embeddings, max_speakers)
        return labels, k, values
    picked = np.linspace(0, count - 1, limit).astype(int)
    labels, k, values = spectral(embeddings[picked], max_speakers)
    centroids = _normalise(np.stack([embeddings[picked][labels == c].mean(0) for c in range(k)]))
    return (embeddings @ centroids.T).argmax(1), k, values


def turns(spans, embeddings, labels, regions, total):
    import numpy as np
    from scipy.ndimage import median_filter

    k = int(labels.max()) + 1
    frames = int(total / STEP) + 1
    score = np.full((frames, k), -1.0)
    centroids = _normalise(np.stack([
        embeddings[labels == c].mean(0) if np.any(labels == c) else np.zeros(embeddings.shape[1]) for c in range(k)
    ]))
    for (begin, end), embedding in zip(spans, embeddings):
        first, last = int(begin / STEP), min(int(end / STEP), frames)
        if last <= first:
            continue
        index = np.arange(first, last)
        middle, half = (begin + end) / 2, (end - begin) / 2 + 1e-9
        weight = 1 - np.abs(index * STEP - middle) / half * 0.5
        sims = centroids @ embedding
        score[index] = np.maximum(score[index], weight[:, None] * sims[None, :])
    speech = np.zeros(frames, dtype=bool)
    for begin, end in regions:
        speech[int(begin / STEP):int(end / STEP)] = True
    frame_labels = np.where(speech, score.argmax(1), -1)
    if speech.any():
        frame_labels[speech] = median_filter(frame_labels[speech], size=MEDIAN_FRAMES, mode="nearest")
    raw = []
    index = 0
    while index < frames:
        if frame_labels[index] >= 0:
            end = index
            while end < frames and frame_labels[end] == frame_labels[index]:
                end += 1
            raw.append((index * STEP, end * STEP, int(frame_labels[index])))
            index = end
        else:
            index += 1
    merged = []
    for begin, end, label in raw:
        if merged and merged[-1][2] == label and begin - merged[-1][1] < MERGE_GAP:
            merged[-1] = (merged[-1][0], end, label)
        else:
            merged.append((begin, end, label))
    return [turn for turn in merged if turn[1] - turn[0] >= MIN_TURN], centroids


def _session(model, threads):
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = max(1, int(threads))
    options.inter_op_num_threads = 1
    options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
    return onnxruntime.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])


def silero_probs(model, threads):
    import numpy as np

    session = _session(model, threads)

    def probs(audio):
        hidden = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros(VAD_CONTEXT, dtype=np.float32)
        rate = np.array(SAMPLE_RATE, dtype=np.int64)
        found = []
        for index in range(len(audio) // VAD_FRAME):
            frame = np.concatenate([context, audio[index * VAD_FRAME:(index + 1) * VAD_FRAME]])[None]
            prob, hidden = session.run(None, {"input": frame, "state": hidden, "sr": rate})
            context = frame[0, -VAD_CONTEXT:]
            found.append(float(prob[0, 0]))
        return found

    return probs


def wespeaker_embedder(model, threads):
    import kaldi_native_fbank as knf
    import numpy as np

    session = _session(model, threads)
    name = session.get_inputs()[0].name
    options = knf.FbankOptions()
    options.frame_opts.dither = 0
    options.frame_opts.snip_edges = True
    options.frame_opts.samp_freq = SAMPLE_RATE
    options.mel_opts.num_bins = 80

    def embed(segment):
        fbank = knf.OnlineFbank(options)
        fbank.accept_waveform(SAMPLE_RATE, (segment * 32768).tolist())
        fbank.input_finished()
        feats = np.stack([fbank.get_frame(i) for i in range(fbank.num_frames_ready)])
        feats = feats - feats.mean(0, keepdims=True)
        vector = session.run(None, {name: feats[None].astype(np.float32)})[0][0]
        return vector / (np.linalg.norm(vector) + 1e-9)

    return embed


def diarize_audio(audio, probs, embed, prints=(), min_speech=MIN_SPEECH_SECONDS):
    import numpy as np

    total = len(audio) / SAMPLE_RATE
    regions = speech_regions(probs(audio), total)
    speech = sum(end - begin for begin, end in regions)
    if speech < min_speech:
        raise TooLittleSpeech(f"only {speech:.0f} s of speech on the others track, need {min_speech:.0f} s")
    spans = windows(regions)
    embeddings = np.stack([
        embed(audio[int(begin * SAMPLE_RATE):int(end * SAMPLE_RATE)]) for begin, end in spans
    ]).astype(np.float32)
    labels, k, values = cluster(embeddings)
    found, centroids = turns(spans, embeddings, labels, regions, total)
    talk = [0.0] * k
    for begin, end, label in found:
        talk[label] += end - begin
    order = sorted((c for c in range(k) if talk[c] > 0), key=lambda c: -talk[c])
    matches = voices_module.match([centroids[c] for c in order], list(prints))
    clusters = []
    renumber = {}
    for position, c in enumerate(order):
        renumber[c] = position
        result = matches[position]
        clusters.append({
            "id": f"S{position + 1}",
            "seconds": round(talk[c], 1),
            "name": result["name"],
            "cosine": result["cosine"],
            "margin": result["margin"],
            "turns": [[round(b, 2), round(e, 2)] for b, e, label in found if label == c],
        })
    window_labels = np.array([renumber.get(int(label), -1) for label in labels], dtype=np.int32)
    summary = {
        "audio_seconds": round(total, 1),
        "speech_seconds": round(speech, 1),
        "windows": len(spans),
        "eigenvalues": [round(float(value), 4) for value in values],
        "clusters": clusters,
    }
    arrays = {
        "embeddings": embeddings,
        "windows": np.array(spans, dtype=np.float32).reshape(-1, 2),
        "labels": window_labels,
    }
    return summary, arrays


def _write_json(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _parse(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def run(cfg, mid, out=None, probs=None, embed=None, decode=None):
    import numpy as np

    st = state.load(cfg.state_path)
    meeting = st["meetings"].get(mid)
    if meeting is None or not meeting.get("end"):
        raise DiarizationError(f"meeting {mid} is unknown or has not ended")
    out = Path(out) if out else cfg.meeting_dir(mid)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    items = others_chunks(
        cfg.audio_dir, _parse(meeting["start"]), _parse(meeting["end"]), floor=state.previous_end(st, mid)
    )
    if not items:
        raise TooLittleSpeech("no others chunks")
    audio, pieces, skipped = assemble(items, decode or (lambda path: decode_chunk(cfg, path)))
    if not pieces:
        raise DiarizationError("no readable others chunk")
    probs = probs or silero_probs(cfg.speech_vad_model, cfg.diarization_threads)
    embed = embed or wespeaker_embedder(cfg.speaker_model, cfg.diarization_threads)
    summary, arrays = diarize_audio(audio, probs, embed, voices_module.load(cfg.voices_dir))
    np.savez(out / SPEAKERS_NPZ, **arrays)
    data = {
        "meeting": mid,
        "status": "ok",
        "threads": cfg.diarization_threads,
        "seconds_taken": round(time.monotonic() - started, 1),
        **summary,
        "chunks": [
            {"name": p.name, "start": state.iso(p.start), "offset": round(p.offset, 3), "seconds": round(p.seconds, 3)}
            for p in pieces
        ],
        "skipped_chunks": skipped,
    }
    _write_json(out / SPEAKERS_JSON, data)
    return data


def overlap_label(begin, end, clusters):
    best, best_overlap = None, 0.0
    for item in clusters:
        covered = 0.0
        for turn_begin, turn_end in item["turns"]:
            covered += max(0.0, min(end, turn_end) - max(begin, turn_begin))
        if covered > best_overlap:
            best, best_overlap = item, covered
    if best is None:
        return None
    return best.get("name") or best["id"]


def labels_for(lines, spans, data):
    pieces = {item["name"]: item for item in data.get("chunks", [])}
    clusters = data.get("clusters", [])
    labels = []
    for line, span in zip(lines, spans):
        side = line[1]
        piece = pieces.get(span.chunk) if span is not None else None
        if side != OTHERS or piece is None:
            labels.append(side)
            continue
        begin = piece["offset"] + span.offset
        stop = span.following if span.following is not None else piece["seconds"]
        end = max(piece["offset"] + stop, begin + 0.1)
        label = overlap_label(begin, end, clusters)
        labels.append(f"{OTHERS}:{label}" if label else OTHERS)
    return labels


def turn_list(data):
    found = []
    for item in data.get("clusters", []):
        name = item.get("name") or item["id"]
        for begin, end in item["turns"]:
            found.append((float(begin), float(end), name))
    return sorted(found)


def track_time(piece, seconds):
    return piece["offset"] + seconds


def word_turn(turns, starts, begin, end, near=NEAR_TURN):
    position = bisect_right(starts, end)
    nearby = turns[max(0, position - 3):position + 2]
    best, best_cover = None, 0.0
    for turn in nearby:
        cover = min(end, turn[1]) - max(begin, turn[0])
        if cover > best_cover:
            best, best_cover = turn, cover
    if best is not None:
        return best
    middle = (begin + end) / 2
    distance = near
    for turn in nearby:
        gap = max(turn[0] - middle, middle - turn[1], 0.0)
        if gap <= distance:
            best, distance = turn, gap
    return best


def _runs(labels):
    found = []
    index = 0
    while index < len(labels):
        stop = index
        while stop < len(labels) and labels[stop] == labels[index]:
            stop += 1
        found.append((index, stop))
        index = stop
    return found


def _backed(labels, found, begin, stop):
    return max(
        (turn[1] - turn[0] for turn, label in zip(found[begin:stop], labels[begin:stop]) if turn and turn[2] == label),
        default=0.0,
    )


def smooth(labels, found, island=ISLAND_WORDS, keep=KEEP_TURN):
    labels = list(labels)
    changed = True
    while changed:
        changed = False
        runs = _runs(labels)
        for number in range(1, len(runs) - 1):
            begin, stop = runs[number]
            if stop - begin > island or _backed(labels, found, begin, stop) >= keep:
                continue
            before, after = labels[runs[number - 1][0]], labels[runs[number + 1][0]]
            if before != after:
                continue
            labels[begin:stop] = [before] * (stop - begin)
            changed = True
            break
    return labels


def cut_score(words, index):
    before = words[index - 1][2]
    score = max(0.0, words[index][0] - words[index - 1][1])
    if before[-1:] in SENTENCE_END:
        score += 1.0
    elif before[-1:] in CLAUSE_END:
        score += 0.4
    if words[index][2].startswith(DIALOGUE_DASHES):
        score += 1.0
    return score


def snap(words, labels, window=SNAP_WINDOW):
    labels = list(labels)
    index = 1
    while index < len(labels):
        if labels[index] == labels[index - 1]:
            index += 1
            continue
        left, right = labels[index - 1], labels[index]
        low = index - 1
        while low > 0 and labels[low - 1] == left:
            low -= 1
        high = index
        while high + 1 < len(labels) and labels[high + 1] == right:
            high += 1
        here = words[index][0]
        candidates = [j for j in range(low + 1, high + 1) if abs(words[j][0] - here) <= window]
        best = max(candidates, key=lambda j: (cut_score(words, j), -abs(j - index)))
        labels[low:high + 1] = [left if k < best else right for k in range(low, high + 1)]
        index = max(best, index) + 1
    return labels


def word_labels(words, turns):
    starts = [turn[0] for turn in turns]
    found = [word_turn(turns, starts, begin, end) for begin, end, _ in words]
    labels = [turn[2] if turn else None for turn in found]
    for index in range(1, len(labels)):
        if labels[index] is None:
            labels[index] = labels[index - 1]
    for index in range(len(labels) - 2, -1, -1):
        if labels[index] is None:
            labels[index] = labels[index + 1]
    return smooth(snap(words, smooth(labels, found)), found)


def _side(label):
    return f"{OTHERS}:{label}" if label else OTHERS


def split_lines(lines, spans, data):
    pieces = {item["name"]: item for item in data.get("chunks", [])}
    turns = turn_list(data)
    fallback = labels_for(lines, spans, data)
    by_chunk = {}
    for index, (line, span) in enumerate(zip(lines, spans)):
        if line[1] == OTHERS and span is not None and span.words and span.chunk in pieces:
            by_chunk.setdefault(span.chunk, []).append(index)
    parts = {}
    for name, indices in by_chunk.items():
        piece = pieces[name]
        indices.sort(key=lambda index: spans[index].offset)
        owners, local, words = [], [], []
        for index in indices:
            for begin, end, text in spans[index].words:
                owners.append(index)
                local.append((begin, text))
                words.append((track_time(piece, begin), track_time(piece, end), text))
        labels = word_labels(words, turns)
        for owner, (begin, text), label in zip(owners, local, labels):
            groups = parts.setdefault(owner, [])
            if groups and groups[-1][0] == label:
                groups[-1][2].append(text)
            else:
                groups.append([label, begin, [text]])
    result = []
    for index, (line, label) in enumerate(zip(lines, fallback)):
        groups = parts.get(index)
        if not groups:
            result.append((line[0], label, line[2]))
        elif len(groups) == 1:
            result.append((line[0], _side(groups[0][0]), line[2]))
        else:
            for name, begin, texts in groups:
                when = line[0] + timedelta(seconds=begin - spans[index].offset)
                result.append((when, _side(name), " ".join(texts)))
    return sorted(result, key=lambda row: row[0])


def thread_env(cfg, environ=None):
    threads = str(max(1, int(cfg.diarization_threads)))
    env = dict(os.environ if environ is None else environ)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[name] = threads
    return env


def subprocess_argv(cfg, mid, self_cmd, low_priority):
    return low_priority(cfg, [*self_cmd, "diarize", mid])


def _self_cmd():
    from .watch import default_self_cmd

    return default_self_cmd()


def _low_priority(cfg, argv):
    from .asr import low_priority

    return low_priority(cfg, argv)


def relabel(cfg, mid, lines, spans, runner=subprocess.run, self_cmd=None, low_priority=None, timeout=TIMEOUT):
    if not lines or not any(line[1] == OTHERS for line in lines):
        return lines, {"status": "skipped", "reason": "no others speech"}
    if not available(cfg):
        return lines, {"status": "skipped", "reason": unavailable_reason(cfg)}
    if len(spans) != len(lines):
        return lines, {"status": "failed", "reason": "segment spans do not match the transcript"}
    out = cfg.meeting_dir(mid)
    out.mkdir(parents=True, exist_ok=True)
    target = out / SPEAKERS_JSON
    target.unlink(missing_ok=True)
    argv = subprocess_argv(cfg, mid, self_cmd or _self_cmd(), low_priority or _low_priority)
    reason = None
    try:
        result = runner(argv, capture_output=True, text=True, timeout=timeout, check=False, env=thread_env(cfg))
        if result.returncode != 0:
            tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
            reason = f"diarize exited {result.returncode}: {tail[0]}".strip()
    except subprocess.TimeoutExpired:
        reason = f"diarize timed out after {timeout} s"
    except OSError as error:
        reason = f"diarize could not start: {error}"
    data = None
    if reason is None:
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            reason = f"speakers.json unreadable: {error}"
    status = "failed"
    if data is not None and data.get("status") != "ok":
        reason = data.get("reason") or f"status {data.get('status')}"
        status = data.get("status") or status
    if reason is not None:
        LOG.warning("diarization of %s %s, keeping plain others: %s", mid, status, reason)
        if data is None:
            _write_json(target, {"meeting": mid, "status": status, "reason": reason})
        return lines, {"status": status, "reason": reason}
    try:
        relabelled = split_lines(lines, spans, data)
    except (KeyError, TypeError, ValueError) as error:
        reason = f"speakers.json malformed: {error}"
        LOG.warning("diarization of %s failed, keeping plain others: %s", mid, reason)
        return lines, {"status": "failed", "reason": reason}
    named = sorted({c["name"] for c in data["clusters"] if c.get("name")})
    return relabelled, {"status": "ok", "speakers": len(data["clusters"]), "named": named}


def main(cfg, mid, out=None):
    try:
        data = run(cfg, mid, out)
    except TooLittleSpeech as error:
        target = (Path(out) if out else cfg.meeting_dir(mid)) / SPEAKERS_JSON
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json(target, {"meeting": mid, "status": "skipped", "reason": str(error)})
        print(f"{mid}: {error}")
        return 0
    summary = ", ".join(
        f"{c['id']} {c['name'] or '-'} {c['seconds']:.0f} s" for c in data["clusters"]
    )
    print(f"{mid}: {len(data['clusters'])} speakers in {data['seconds_taken']} s: {summary}")
    return 0
