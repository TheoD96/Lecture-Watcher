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
import re
import shutil
import subprocess
import sys
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


def require(binary):
    if not shutil.which(binary):
        sys.exit(f"error: '{binary}' not found on PATH. Install it first.")


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

    require("ffmpeg")
    log("downloading with ffmpeg...")
    run(["ffmpeg", "-y", "-loglevel", "error", "-stats", "-i", source,
         "-c", "copy", str(dest)])
    return dest


def has_video(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout
    return "video" in out


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


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


def transcribe(media, out_dir, model_size, language):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("error: faster-whisper not installed. Run:\n"
                 "  pip install -r skills/watch-lecture/scripts/requirements.txt\n"
                 "or pass --captions with Echo360's caption file.")

    audio = out_dir / "audio.wav"
    if not audio.exists():
        log("extracting audio...")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(media),
             "-vn", "-ac", "1", "-ar", "16000", str(audio)])

    # decode the wav ourselves so faster-whisper never touches PyAV,
    # which breaks whenever the av and faster-whisper versions drift apart
    import wave
    import numpy as np
    with wave.open(str(audio)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    samples = pcm.astype(np.float32) / 32768.0

    log(f"transcribing with whisper '{model_size}' (this is the slow bit)...")
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    seg_iter, info = model.transcribe(
        samples, language=language, vad_filter=True, beam_size=5,
        initial_prompt="University lecture.")
    total = info.duration or 1
    segs = []
    for s in seg_iter:
        segs.append({"start": s.start, "end": s.end, "text": s.text.strip()})
        print(f"\r[lecture] {fmt_ts(s.end)} / {fmt_ts(total)}", end="",
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
    """Grab a frame at each scene change (i.e. new slide), deduped."""
    frames_dir = out_dir / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir()
    tmp = frames_dir / "_raw"
    tmp.mkdir()

    log("detecting slide changes...")
    # always keep the first frame, then every scene change above threshold
    vf = (f"select='eq(n\\,0)+gt(scene\\,{threshold})',"
          f"showinfo,scale={width}:-2")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-i", str(media), "-vf", vf,
         "-fps_mode", "vfr", "-q:v", "3", str(tmp / "%05d.jpg")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit("ffmpeg frame extraction failed:\n" + proc.stderr[-2000:])

    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", proc.stderr)]
    raw = sorted(tmp.glob("*.jpg"))
    pairs = list(zip(times, raw))

    kept, last_t, last_hash = [], -1e9, None
    for t, path in pairs:
        h = _ahash(path)
        if t - last_t < min_gap and kept:
            # slide changed again quickly (animation/build), keep the later one
            kept[-1] = (kept[-1][0], path)
            last_hash = h
            continue
        if last_hash is not None and h is not None and _hamming(h, last_hash) <= 4:
            continue
        kept.append((t, path))
        last_t, last_hash = t, h

    # if there are way too many, thin them evenly
    if len(kept) > max_frames:
        step = len(kept) / max_frames
        kept = [kept[int(i * step)] for i in range(max_frames)]

    result = []
    for i, (t, path) in enumerate(kept, 1):
        name = f"{i:03d}_{fmt_ts(t).replace(':', '-')}.jpg"
        path.rename(frames_dir / name)
        result.append({"time": t, "file": f"frames/{name}"})
    shutil.rmtree(tmp)
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
    ap.add_argument("--model", default="small",
                    help="whisper model: tiny/base/small/medium/large-v3 (default small)")
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

    require("ffmpeg")
    require("ffprobe")

    name = args.title or Path(args.source.split("?")[0]).stem or "lecture"
    slug = re.sub(r"[^\w-]+", "-", name).strip("-").lower() or "lecture"
    out_dir = Path(args.out or Path("lectures") / slug).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    media = fetch(args.source, out_dir, args.cookies, args.browser)
    total = duration(media)
    log(f"source: {media} ({fmt_ts(total)})")

    segs = []
    if args.captions:
        segs = parse_captions(args.captions)
        log(f"loaded {len(segs)} caption cues")
    elif not args.no_transcript:
        segs = transcribe(media, out_dir, args.model, args.language)
    if segs:
        write_transcript(segs, out_dir)

    frames = []
    if not args.no_frames and has_video(media):
        frames = extract_frames(media, out_dir, args.threshold, args.min_gap,
                                args.max_frames, args.width)

    write_index(segs, frames, out_dir, name, total)
    (out_dir / "audio.wav").unlink(missing_ok=True)
    print(out_dir.resolve())


if __name__ == "__main__":
    main()
