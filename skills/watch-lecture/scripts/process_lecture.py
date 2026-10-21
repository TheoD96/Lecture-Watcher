#!/usr/bin/env python3
"""Turn a lecture recording into something Claude can "watch".

Produces, in the output dir:
  transcript.md   timestamped transcript
  segments.json   raw transcript segments
  frames/         one JPG per distinct slide / scene change
  index.md        frames interleaved with what was said while each was on screen

Usage:
  process_lecture.py SOURCE [-o OUT] [--captions FILE] [--cookies FILE] ...
SOURCE can be a local video/audio file, a direct .mp4 URL, or an HLS .m3u8 URL.
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".ts"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}


def log(msg):
    print(f"[lecture] {msg}", file=sys.stderr, flush=True)


def fmt_ts(seconds):
    s = int(seconds)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def find_ffmpeg():
    """System ffmpeg if there is one, else the binary bundled with imageio-ffmpeg
    (pip installable, handy in sandboxes like Cowork where you can't brew/apt)."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("error: ffmpeg not found. Install it (brew install ffmpeg) "
                 "or run: pip install imageio-ffmpeg")


FFMPEG = None


# ---------------------------------------------------------------- fetching

def fetch(source, out_dir, cookies=None, browser=None):
    """Return a local media path, downloading if SOURCE is a URL."""
    if not re.match(r"^https?://", source):
        path = Path(source).expanduser()
        if not path.exists():
            sys.exit(f"error: {path} does not exist")
        return path

    dest = out_dir / "source.mp4"
    if dest.exists():
        log(f"reusing {dest}")
        return dest

    if shutil.which("yt-dlp"):
        cmd = ["yt-dlp", "-o", str(dest), "--merge-output-format", "mp4",
               "-N", "8",  # download HLS fragments 8 at a time
               "--ffmpeg-location", FFMPEG,
               "-f", "bv*+ba/b", "--no-playlist"]
        if cookies:
            cmd += ["--cookies", cookies]
        if browser:
            cmd += ["--cookies-from-browser", browser]
        log("downloading with yt-dlp...")
        try:
            run(cmd + [source])
            return dest
        except subprocess.CalledProcessError:
            log("yt-dlp failed, falling back to ffmpeg")

    log("downloading with ffmpeg...")
    run([FFMPEG, "-y", "-loglevel", "error", "-stats", "-i", source,
         "-c", "copy", str(dest)])
    return dest


def probe(path):
    """Return (duration_secs, has_video). Parses `ffmpeg -i` so ffprobe isn't needed."""
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
    return dur, bool(re.search(r"Stream #.*: Video:", err))


# ---------------------------------------------------------------- transcript

def parse_captions(path):
    """Parse a .vtt or .srt file into [{start, end, text}]."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    ts = r"(\d+:)?\d{1,2}:\d{2}[.,]\d{3}"
    cue_re = re.compile(rf"({ts})\s*-->\s*({ts})[^\n]*\n(.*?)(?:\n\s*\n|\Z)", re.S)

    def secs(t):
        parts = t.replace(",", ".").split(":")
        parts = [float(p) for p in parts]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]

    segs, last = [], None
    for m in cue_re.finditer(text):
        body = re.sub(r"<[^>]+>", "", m.group(5)).strip()
        body = re.sub(r"\s+", " ", body)
        # auto captions often repeat the previous line, skip exact dupes
        if not body or body == last:
            continue
        last = body
        segs.append({"start": secs(m.group(1)), "end": secs(m.group(3)), "text": body})
    return segs


MLX_REPOS = {"turbo": "mlx-community/whisper-large-v3-turbo",
             "large-v3-turbo": "mlx-community/whisper-large-v3-turbo"}
PROMPT = "University lecture."


def pick_backend(backend):
    if backend != "auto":
        return backend
    # Apple Silicon: run on the GPU with MLX, way faster than CPU whisper
    if sys.platform == "darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
            return "mlx"
        except ImportError:
            log("tip: pip install mlx-whisper for much faster transcription on this Mac")
    return "faster-whisper"


def load_audio(media, out_dir):
    audio = out_dir / "audio.wav"
    if not audio.exists():
        log("extracting audio...")
        run([FFMPEG, "-y", "-loglevel", "error", "-i", str(media),
             "-vn", "-ac", "1", "-ar", "16000", str(audio)])

    # decode the wav ourselves so faster-whisper never touches PyAV,
    # which breaks whenever the av and faster-whisper versions drift apart
    import wave
    import numpy as np
    with wave.open(str(audio)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    return pcm.astype(np.float32) / 32768.0


def transcribe(media, out_dir, model, language, backend):
    samples = load_audio(media, out_dir)
    backend = pick_backend(backend)
    if backend == "mlx":
        return _transcribe_mlx(samples, model or "turbo", language)
    return _transcribe_fw(samples, model or "small", language)


def _transcribe_mlx(samples, model, language):
    import mlx_whisper
    repo = model if "/" in model else MLX_REPOS.get(model, f"mlx-community/whisper-{model}-mlx")
    log(f"transcribing on the GPU with MLX ({repo})...")
    res = mlx_whisper.transcribe(samples, path_or_hf_repo=repo, language=language,
                                 initial_prompt=PROMPT, verbose=False)
    return [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in res["segments"]]


def _transcribe_fw(samples, model, language):
    try:
        from faster_whisper import BatchedInferencePipeline, WhisperModel
    except ImportError:
        sys.exit("error: faster-whisper not installed. Run:\n"
                 "  pip install -r skills/watch-lecture/scripts/requirements.txt\n"
                 "or pass --captions with Echo360's caption file.")

    log(f"transcribing with whisper '{model}' (this is the slow bit)...")
    wm = WhisperModel(model, device="auto", compute_type="auto",
                      cpu_threads=os.cpu_count() or 4)
    # batched mode transcribes chunks in parallel, ~2-4x faster than sequential
    seg_iter, info = BatchedInferencePipeline(wm).transcribe(
        samples, language=language, batch_size=8, beam_size=1,
        initial_prompt=PROMPT)
    total = info.duration or 1
    segs = []
    for seg in seg_iter:
        segs.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        print(f"\r[lecture] {fmt_ts(seg.end)} / {fmt_ts(total)}", end="",
              file=sys.stderr, flush=True)
    print(file=sys.stderr)
    return segs


def write_transcript(segs, out_dir, para_secs=60):
    """Group segments into ~1 minute paragraphs so it's easy to skim."""
    lines, buf, start = [], [], None
    for s in segs:
        if start is None:
            start = s["start"]
        buf.append(s["text"])
        if s["end"] - start >= para_secs:
            lines.append(f"**[{fmt_ts(start)}]** {' '.join(buf)}\n")
            buf, start = [], None
    if buf:
        lines.append(f"**[{fmt_ts(start)}]** {' '.join(buf)}\n")
    (out_dir / "transcript.md").write_text("# Transcript\n\n" + "\n".join(lines))
    (out_dir / "segments.json").write_text(json.dumps(segs, indent=1))


# ---------------------------------------------------------------- frames

def extract_frames(media, out_dir, threshold, min_gap, max_frames, width):
    """Grab a frame at each scene change (i.e. new slide), deduped.

    Detection runs on 1 fps 320px thumbnails, which is far cheaper than scoring
    every full-res frame. Then only the kept moments are grabbed at full size."""
    frames_dir = out_dir / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir()
    tmp = frames_dir / "_thumbs"
    tmp.mkdir()

    log("detecting slide changes...")
    # always keep the first frame, then every scene change above threshold
    vf = f"fps=1,scale=320:-2,select='eq(n\\,0)+gt(scene\\,{threshold})',showinfo"
    proc = subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-hwaccel", "auto", "-an", "-sn",
         "-i", str(media), "-vf", vf, "-fps_mode", "vfr", "-q:v", "5",
         str(tmp / "%05d.jpg")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit("ffmpeg frame extraction failed:\n" + proc.stderr[-2000:])

    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", proc.stderr)]
    pairs = list(zip(times, sorted(tmp.glob("*.jpg"))))

    # (label time, time of the image to grab)
    kept, last_t, last_hash = [], -1e9, None
    for t, path in pairs:
        h = _ahash(path)
        if t - last_t < min_gap and kept:
            # slide changed again quickly (animation/build), keep the later one
            kept[-1] = (kept[-1][0], t)
            last_hash = h
            continue
        if last_hash is not None and h is not None and _hamming(h, last_hash) <= 4:
            continue
        kept.append((t, t))
        last_t, last_hash = t, h
    shutil.rmtree(tmp)

    # if there are way too many, thin them evenly
    if len(kept) > max_frames:
        step = len(kept) / max_frames
        kept = [kept[int(i * step)] for i in range(max_frames)]

    def grab(item):
        i, (label, at) = item
        name = f"{i:03d}_{fmt_ts(label).replace(':', '-')}.jpg"
        # +0.5s lands safely inside the new slide; retry exact time if that's past the end
        for seek in (at + 0.5, at):
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{seek:.2f}",
                            "-i", str(media), "-frames:v", "1", "-vf", f"scale={width}:-2",
                            "-q:v", "3", str(frames_dir / name)], check=True)
            if (frames_dir / name).exists():
                break
        return {"time": label, "file": f"frames/{name}"}

    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(grab, enumerate(kept, 1)))
    log(f"kept {len(result)} frames (from {len(pairs)} scene changes)")
    return result


def _ahash(path):
    try:
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(path).convert("L").resize((16, 16))
    px = img.tobytes()
    avg = sum(px) / len(px)
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def _hamming(a, b):
    return bin(a ^ b).count("1")


# ---------------------------------------------------------------- index

def write_index(segs, frames, out_dir, title, total):
    out = [f"# {title}\n",
           f"Duration: {fmt_ts(total)} | Frames: {len(frames)} | "
           f"Transcript segments: {len(segs)}\n",
           "Each section is one slide/scene. View the frame image, then read "
           "what was said while it was on screen.\n"]

    if not frames:
        out.append("_No video frames (audio only)._\n")
        out.append(" ".join(s["text"] for s in segs))
    else:
        bounds = [f["time"] for f in frames] + [float("inf")]
        for i, f in enumerate(frames):
            lo, hi = bounds[i], bounds[i + 1]
            # anything said before the first frame goes in the first section
            said = [s["text"] for s in segs
                    if (s["start"] >= lo or i == 0) and s["start"] < hi]
            end = fmt_ts(hi) if hi != float("inf") else fmt_ts(total)
            out.append(f"## [{fmt_ts(lo)} - {end}] Frame {i + 1}\n")
            out.append(f"![]({f['file']})\n")
            out.append((" ".join(said) or "_(nothing said)_") + "\n")
    (out_dir / "index.md").write_text("\n".join(out))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="video/audio file, .mp4 URL or .m3u8 URL")
    ap.add_argument("-o", "--out", help="output dir (default: ./lectures/<name>)")
    ap.add_argument("--title", help="lecture title for index.md")
    ap.add_argument("--captions", help=".vtt/.srt captions, skips whisper")
    ap.add_argument("--cookies", help="Netscape cookies.txt for yt-dlp")
    ap.add_argument("--cookies-from-browser", dest="browser",
                    help="let yt-dlp read cookies from e.g. chrome, firefox, safari")
    ap.add_argument("--model",
                    help="whisper model: tiny/base/small/medium/large-v3/turbo "
                         "(default: turbo with MLX, small otherwise)")
    ap.add_argument("--backend", default="auto", choices=["auto", "mlx", "faster-whisper"],
                    help="auto uses MLX (GPU) on Apple Silicon if installed")
    ap.add_argument("--language", default="en")
    ap.add_argument("--threshold", type=float, default=0.12,
                    help="scene change sensitivity, lower = more frames (default 0.12)")
    ap.add_argument("--min-gap", type=float, default=8,
                    help="min seconds between frames (default 8)")
    ap.add_argument("--max-frames", type=int, default=80)
    ap.add_argument("--width", type=int, default=1280, help="frame width px")
    ap.add_argument("--no-frames", action="store_true")
    ap.add_argument("--no-transcript", action="store_true")
    args = ap.parse_args()

    global FFMPEG
    FFMPEG = find_ffmpeg()

    name = args.title or Path(args.source.split("?")[0]).stem or "lecture"
    slug = re.sub(r"[^\w-]+", "-", name).strip("-").lower() or "lecture"
    out_dir = Path(args.out or Path("lectures") / slug).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    media = fetch(args.source, out_dir, args.cookies, args.browser)
    total, video = probe(media)
    log(f"source: {media} ({fmt_ts(total)})")

    # slides and transcript are independent, so do them at the same time
    with ThreadPoolExecutor(max_workers=1) as pool:
        frames_job = None
        if not args.no_frames and video:
            frames_job = pool.submit(extract_frames, media, out_dir, args.threshold,
                                     args.min_gap, args.max_frames, args.width)
        segs = []
        if args.captions:
            segs = parse_captions(args.captions)
            log(f"loaded {len(segs)} caption cues")
        elif not args.no_transcript:
            segs = transcribe(media, out_dir, args.model, args.language, args.backend)
        if segs:
            write_transcript(segs, out_dir)
        frames = frames_job.result() if frames_job else []

    write_index(segs, frames, out_dir, name, total)
    (out_dir / "audio.wav").unlink(missing_ok=True)
    print(out_dir.resolve())


if __name__ == "__main__":
    main()
