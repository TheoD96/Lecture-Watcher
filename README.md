# Lecture Watcher

A Claude Code plugin that lets Claude "watch" recorded lectures (Echo360, Panopto,
YouTube, Zoom, or any local video). It transcribes the audio with Whisper, grabs a
frame every time the slide changes, lines the two up, and then Claude reads the lot
and writes study notes, summaries, quizzes, or answers questions about the lecture.

## Install

Needs `ffmpeg` and Python 3.9+.

```bash
# ffmpeg
brew install ffmpeg            # mac
winget install ffmpeg          # windows
sudo apt install ffmpeg        # linux

# python deps
pip install -r skills/watch-lecture/scripts/requirements.txt
```

Then in Claude Code:

```
/plugin marketplace add theod96/lecture-watcher
/plugin install lecture-watcher@lecture-watcher
```

Or just copy `skills/watch-lecture` into `~/.claude/skills/` to use it as a plain skill.

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
python3 skills/watch-lecture/scripts/process_lecture.py lecture.mp4 --title "INFO213 Week 4"
```

Outputs to `lectures/<title>/`: `index.md` (slides + what was said), `transcript.md`,
`frames/*.jpg`, `segments.json`. Run with `-h` for all options (whisper model size,
slide detection sensitivity, etc).

For personal study only. Don't redistribute lecture recordings.
