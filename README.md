# Lecture Watcher

A Claude Code plugin that lets Claude "watch" recorded lectures (Echo360, Panopto,
YouTube, Zoom, or any local video). It transcribes the audio with Whisper, grabs a
frame every time the slide changes, lines the two up, and then Claude reads the lot
and writes study notes, summaries, quizzes, or answers questions about the lecture.

## Requirements

### Everywhere

| Need | Why | Notes |
|---|---|---|
| Claude Code (CLI, desktop or IDE extension) | Runs the skill | Or Cowork, see below |
| Python 3.9+ with pip | Runs `process_lecture.py` | |
| Python packages from `requirements.txt` | `faster-whisper` (transcription), `numpy`, `Pillow` (slide dedupe), `yt-dlp` (downloads), `imageio-ffmpeg` (bundled ffmpeg), `mlx-whisper` (Apple Silicon only) | |
| ffmpeg 5.1+ | Audio extraction, slide detection, HLS downloads | Optional: `imageio-ffmpeg` bundles one |
| Internet on first run | Whisper model download from Hugging Face (~500 MB for `small`, ~1.6 GB for `turbo`) | Cached after that. Not needed with `--captions` |
| Disk space | `source.mp4` for a 1 h lecture is ~0.3-1 GB | Delete it once notes are done |
| Claude in Chrome extension (optional) | Lets Claude find a lecture on Learn/Echo360 by name | Without it, give Claude the file, `.m3u8` URL or captions |

### Mac

1. Python 3.9+: the one from python.org or `brew install python` (the Xcode Command Line Tools `python3` also works).
2. ffmpeg (optional): `brew install ffmpeg`
3. Python deps:
   ```bash
   python3 -m pip install -r skills/watch-lecture/scripts/requirements.txt
   ```
   On Homebrew Python, pip may refuse with "externally managed environment". Add
   `--user --break-system-packages`, or use a venv.
4. Apple Silicon (M1 and later): `mlx-whisper` installs automatically and transcribes on the GPU,
   roughly a few minutes per hour of lecture. Intel Macs use faster-whisper on the CPU.
5. `--cookies-from-browser chrome|safari` works, but macOS will ask for Keychain
   access (Chrome) or Full Disk Access for the terminal (Safari) the first time.

### Windows

1. **Git for Windows** ([git-scm.com](https://git-scm.com/download/win)). Claude Code on Windows runs
   shell commands through Git Bash, and the skill's commands are written for bash.
2. Python 3.9+: `winget install Python.Python.3.12` (or python.org, tick *Add python.exe to PATH*).
   Turn off the Microsoft Store `python3` alias in *Settings → Apps → Advanced app settings →
   App execution aliases* if `python3` opens the Store. Otherwise use `py`/`python` in place of `python3`.
3. ffmpeg (optional): `winget install --id Gyan.FFmpeg`, then open a new terminal so it's on PATH.
4. Python deps:
   ```powershell
   py -m pip install -r skills/watch-lecture/scripts/requirements.txt
   ```
   You may get a Hugging Face warning about symlinks on the first model download. It's harmless.
   Turning on Developer Mode silences it and saves disk space.
5. Transcription runs on the CPU (`small` model: very roughly a quarter to half of the
   lecture's length). With an NVIDIA GPU, faster-whisper uses CUDA automatically, but only if
   CUDA 12 cuBLAS and cuDNN 9 are installed (`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`).
   If it errors about `cudnn`/`cublas`, install those or pass `--device cpu`.
6. `--cookies-from-browser chrome` usually **fails on Windows**: Chrome 127+ encrypts cookies so
   other apps can't read them. Use `--cookies-from-browser firefox`, or export a `cookies.txt`
   with a "Get cookies.txt" extension and pass `--cookies cookies.txt`.

### Check it works

```bash
python3 skills/watch-lecture/scripts/process_lecture.py -h   # Windows: py ...
python3 -c "import faster_whisper, yt_dlp, imageio_ffmpeg, PIL; print('ok')"
```

## Install the plugin

Then in Claude Code:

```
/plugin marketplace add theod96/lecture-watcher
/plugin install lecture-watcher@lecture-watcher
```

Or just copy `skills/watch-lecture` into `~/.claude/skills/` to use it as a plain skill.

**Cowork:** install `dist/lecture-watcher.plugin` from the Claude desktop app. Download the
lecture (or its captions) into a folder first and share that folder with Cowork. System ffmpeg
is optional, the pip requirements include a bundled one.

## Use

Just ask Claude:

> make notes from this lecture ~/Downloads/COSC101_wk3.mp4

> watch this echo360 lecture and quiz me on it: https://content.echo360.org.au/.../s1_av.m3u8?...

> here's the captions file from echo360, summarise the lecture: ~/Downloads/lecture.vtt

### Getting Echo360 recordings

- **Download enabled**: lesson's `...` menu → *Download original*. Easiest.
- **Captions**: if Echo360 has a transcript, download the `.vtt`. Skips Whisper so it's way faster.
- **Stream only**: open DevTools → Network, filter `m3u8`, press play, copy the playlist
  URL (whole thing, including the query string). These expire after a few hours.
- **Needs login**: Claude runs the script with `--cookies-from-browser chrome` to use your
  existing session.

## Running the script directly

```bash
python3 skills/watch-lecture/scripts/process_lecture.py lecture.mp4 --title "INFO213 Week 4"   # Windows: py ...
```

Outputs to `lectures/<title>/`: `index.md` (slides + what was said), `transcript.md`,
`frames/*.jpg`, `segments.json`. Run with `-h` for all options (whisper model size,
slide detection sensitivity, etc).

For personal study only. Don't redistribute lecture recordings.
