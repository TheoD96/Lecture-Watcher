---
name: watch-lecture
description: Find, watch and listen to recorded lectures (Echo360, Panopto, YouTube, Zoom, or any local video/audio file). Can browse the user's LMS (e.g. UC Learn) and Echo360 in their browser to find a recording, then transcribes the audio and pulls out each slide as an image to produce study notes, summaries, quizzes, or answer questions. Use when the user names a lecture ("watch COSC121 week 4 lecture 2", "catch me up on yesterday's lecture"), shares a lecture recording, Echo360 link, .m3u8 stream or caption file, or asks to "watch", "summarise", or "make notes from" a lecture.
---

# Watch Lecture

Claude can't play video directly, so this skill converts a recording into
two things Claude can read: a timestamped **transcript** (what was said) and
a set of **frames** (one image per slide change). `index.md` interleaves them
so each slide sits next to what the lecturer said while it was up.

## 1. Get the recording

If the user **named** a lecture instead of giving a file/URL (e.g. "watch COSC121
week 4", "catch me up on yesterday's INFO213 lecture"), find it in their browser:
follow `references/finding-recordings.md`. It opens Learn, goes to the course's
Echo360 page, and grabs the captions, download, or stream URL.

Otherwise, work out what the user gave you:

| Input | What to do |
|---|---|
| Local `.mp4` / `.m4a` / etc. | Pass the path straight in |
| Echo360 **downloaded** file | Same as above. In Echo360: lesson's `...` menu → *Download original* (only if the lecturer allowed downloads) |
| Echo360 `.m3u8` stream URL | Pass the URL. See "Echo360 streams" below for how to get it |
| Echo360 caption file (`.vtt`/`.srt`) | Pass with `--captions FILE`. Skips Whisper, much faster. Still pass the video too if you have it, for slides |
| YouTube / other public page | Pass the URL, yt-dlp handles it |
| Echo360 / Learn page link | Open it in the browser and follow `references/finding-recordings.md` from step 5. No browser tool? Ask for a download, the `.m3u8`, or use cookies (below) |

### Echo360 streams

If there's no browser tool and downloads are disabled, the user can grab the stream URL by hand:

1. Open the lecture in Echo360 in Chrome/Firefox, open DevTools → **Network** tab
2. Filter for `m3u8`, press play
3. Copy the URL of the master playlist (usually ends `.../s1_av.m3u8` or similar,
   on `content.echo360.org.au` for NZ/AU). The signed query string matters, copy the whole thing
4. Give it to you. It expires after a few hours, so process it promptly

If the URL needs the login session, use `--cookies-from-browser chrome` (works
when Claude Code runs on the user's own machine) or `--cookies cookies.txt`
exported with a "Get cookies.txt" browser extension.

## 2. Process it

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/skills/watch-lecture/scripts/process_lecture.py" SOURCE \
  --title "COSC101 Week 3 Lecture 1" -o lectures/cosc101-w3l1
```

If the script isn't found at that path, locate it with
`find ~ -path '*watch-lecture/scripts/process_lecture.py' 2>/dev/null | head -1`.

First run: if it errors about `faster-whisper` or ffmpeg, install deps with
`pip install -r <skill dir>/scripts/requirements.txt`. That includes
`imageio-ffmpeg`, which bundles an ffmpeg binary, so a system ffmpeg is optional.
If pip refuses with "externally managed environment", retry with
`pip install --user --break-system-packages -r ...` or use a venv.

In a sandbox (e.g. Cowork): the recording must be in a folder the user has
shared with you. Browser cookies aren't reachable, so ask the user to download
the video or captions from Echo360 first. If pip or the Whisper model download
is blocked by the network, tell the user and fall back to `--captions` (or
reading the caption file and slides PDF directly) instead.

Useful flags:
- `--captions FILE` use existing captions instead of transcribing. By far the
  fastest option (seconds, not minutes), so always look for Echo360 captions first
- `--backend auto|mlx|faster-whisper`. `auto` uses MLX on the GPU on Apple Silicon
  Macs when `mlx-whisper` is installed (the requirements file installs it there),
  otherwise batched faster-whisper on the CPU. If the script prints a tip about
  mlx-whisper, install it: it's several times faster on M-series Macs
- `--model tiny|base|small|medium|large-v3|turbo`. Default is `turbo` on MLX
  (fast and accurate) and `small` on CPU. On CPU go `medium` for heavy accents or
  jargon if the user has time, `tiny` for a quick first pass
- `--threshold 0.12` slide-change sensitivity. Raise (0.2-0.3) if there are too many
  near-duplicate frames (e.g. lecturer cam in shot), lower (0.06) if slides are being missed
- `--min-gap 8` minimum seconds between frames
- `--no-frames` audio-only lectures or when slides were shared separately

Slide detection and transcription run in parallel. Transcription is still the
slow part without captions, so run long recordings in the background and tell the
user roughly how long (CPU `small`: very roughly a quarter to half the lecture's
length; MLX on Apple Silicon: a few minutes for an hour). For several lectures,
run them one after another rather than in parallel, each one already uses every core. Output dir is reused, so a re-run after a failure
won't re-download.

## 3. Watch it

The script prints the output dir. In it:

- `index.md` - start here. One section per slide: timestamp, frame path, what was said
- `transcript.md` - full transcript in ~1 min paragraphs with timestamps
- `frames/NNN_MM-SS.jpg` - slide images
- `segments.json` - raw segments, if you need exact timings

Read `index.md` in full. Then **view the frames** with the Read tool. For a
normal slide deck lecture (under ~60 frames) look at all of them, since slides
hold the diagrams, equations, code and definitions the audio skips over. For
lots of frames, prioritise ones where the transcript says "as you can see",
"this diagram", "this equation", "on the slide", etc.

Watch for:
- Things said but not on slides (often exam hints: "this will be in the test",
  "important", "people always get this wrong")
- Things on slides but not said (formulas, code, references)
- Whisper mishearing jargon. Fix obvious errors using the slide text (e.g.
  "sequel" → SQL, course codes, names)

## 4. Output

Default to study notes saved as `notes.md` in the output dir, unless the user
asked for something else (quiz, flashcards, just a summary, a specific question):

```markdown
# <Course> - <Lecture title>
> <1-3 sentence summary>

## Key points
- ...

## Notes
### <Topic> [mm:ss]
... (follow the lecture's structure, include formulas/code/diagram descriptions from slides)

## Definitions
- **Term**: definition

## Flagged by the lecturer
- [mm:ss] "This will be on the exam..." etc.

## Questions to check understanding
1. ...
```

Include timestamps so the user can jump back to that bit of the recording.
Use NZ English spelling. Don't use em dashes in the notes.

## Notes

- These recordings are for the user's personal study. Don't suggest
  redistributing downloaded lecture content.
- `source.mp4` in the output dir can be large. Mention the user can delete it
  once notes are done.
