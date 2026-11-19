# screenpipe

screenpipe records the screen and audio on charon. The package lives in
`pkgs/screenpipe/package.nix` and the user service in
`hosts/charon/modules/screenpipe.nix`.

The service records the screen only, with `--disable-audio`. Audio is left to
`meeting-notes` (see [meeting-notes.md](meeting-notes.md)): on two 45 min
French calls, screenpipe's own transcription kept about half of what was said,
with English filler, shuffled segments and wrong names, where whisper large-v3
in `meeting-notes` kept over 90 %. `--language french --language english`
stays for the OCR language hint.

## OCR wrapper

On Linux, screenpipe runs the `tesseract` binary that ships next to its own
executable, once per captured frame, on the full 3840x2160 screenshot. Plain
tesseract takes 1.7s on a terminal frame and 5.3s on a busy Slack frame, uses
one core, and misses a lot of small UI text. Frames then queue up and
screenpipe drops them after 15s.

The package renames the bundled binary to `tesseract-real` and installs
`pkgs/screenpipe/ocrwrap.py` as `tesseract` in its place. screenpipe calls it
with the same arguments and reads the same TSV output. The wrapper:

1. Decodes the frame to grayscale and computes a Sobel edge map with one
   ffmpeg call.
2. Erases long single-row horizontal rules (terminal separators), because
   tesseract misreads text sitting on them.
3. Splits the frame into text boxes with a recursive XY cut: blank columns
   first, then blank rows. Columns that are inked over most of a region's
   height (pane borders) are ignored, and regions with no blank row are cut at
   their least-inked rows. Empty screen area is never sent to tesseract.
4. Inverts boxes whose most common gray value is dark, so light-on-dark text
   reads correctly.
5. Runs tesseract (`--psm 6`) on all boxes at native scale, batching many
   boxes per process through tesseract's image-list input so each process
   loads the model once, with one batch per CPU.
6. Retries boxes whose mean word confidence is below 80 at 2x scale, and keeps
   whichever attempt scores higher (confidence times alphanumeric characters).
7. Merges the per-box TSV back into frame coordinates.

Any failure falls back to running `tesseract-real` with the original
arguments. Calls that are not a `stdout ... tsv` OCR request, such as
`--version`, pass straight through.

The wrapper lowers its own priority to nice 10 so OCR bursts do not compete
with foreground work.

### Measured on charon (i9-14900K)

Recall is the share of visible words found, scored against a hand-transcribed
ground truth.

| Frame | Plain tesseract | Wrapper |
|---|---|---|
| Terminal (Ghostty, 4K) | 1.8s, 93.0% | 0.9s, 99.1% (every terminal word; misses are status-bar pills) |
| Slack plus herdr (4K) | 5.3s, 59.9% | 1.9s, 93.9% |

CPU time per frame is about 4s for the terminal frame and 20s for the Slack
frame, spread across all cores.

### Tuning

Environment variables on the screenpipe service override the defaults:

- `OW_CANDIDATES`: comma-separated `psm:scale` passes, tried in order on
  boxes still below the confidence threshold. Default `6:1,6:2`. `6:1` alone
  halves CPU at about 87% recall on busy UI frames. `6:1,6:2,11:2` reaches 96%
  on Slack at about 1.5x the CPU.
- `OW_ACCEPT`: mean word confidence that stops further passes. Default 80.
- `OW_LANG`: tesseract language string. Defaults to the `-l` value screenpipe
  passes. charon sets `eng+fra`: `eng` alone already reads most French accents
  but misses some (`coûts`, `Peïo`), `fra` alone drops English words in the
  terminal, and `eng+fra` keeps both at about 1.7x the CPU of `eng`. The
  package ships `fra.traineddata` from nixpkgs next to the bundled English
  model.
- `OW_NICE`: nice increment for the wrapper and its tesseract processes.
  Default 10.
- `OW_WORKERS`: number of parallel tesseract batches. Defaults to the CPU
  count.
- `OW_PROFILE=1`: logs per-stage timings to stderr.
