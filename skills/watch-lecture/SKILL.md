---
name: watch-lecture
description: Watch and listen to a recorded lecture (Echo360, Panopto, YouTube, Zoom recording, or any local video/audio file) by transcribing the audio and pulling out each slide as an image, then produce study notes, summaries, or answer questions about it. Use when the user shares a lecture recording, an Echo360 link or .m3u8 stream, a lecture caption/transcript file, or asks to "watch", "summarise", or "make notes from" a lecture.
---

# Watch Lecture

Claude can't play video directly, so this skill converts a recording into
two things Claude can read: a timestamped **transcript** (what was said) and
a set of **frames** (one image per slide change). `index.md` interleaves them
so each slide sits next to what the lecturer said while it was up.

## 1. Get the recording

Work out what the user gave you:

| Input | What to do |
|---|---|
| Local `.mp4` / `.m4a` / etc. | Pass the path straight in |
| Echo360 **downloaded** file | Same as above. In Echo360: lesson's `...` menu → *Download original* (only if the lecturer allowed downloads) |
| Echo360 `.m3u8` stream URL | Pass the URL. See "Echo360 streams" below for how to get it |
| Echo360 caption file (`.vtt`/`.srt`) | Pass with `--captions FILE`. Skips Whisper, much faster. Still pass the video too if you have it, for slides |
| YouTube / other public page | Pass the URL, yt-dlp handles it |
| Plain Echo360 page link only | You can't log in to Echo360 yourself. Ask the user for a download, the `.m3u8`, or a cookies file (see below) |

### Echo360 streams

If downloads are disabled, the user can grab the stream URL:

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

First run: if it errors about `faster-whisper`, install deps with
`pip install -r <skill dir>/scripts/requirements.txt` (needs `ffmpeg` on PATH too:
`brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install ffmpeg`).

Useful flags:
- `--captions FILE` use existing captions instead of transcribing
- `--model tiny|base|small|medium|large-v3` (default `small`). `small` is a good
  balance. Go `medium` for heavy accents or technical jargon if the user has time/a GPU.
  `tiny` for a quick first pass. A 50 min lecture on `small` takes roughly 5-15 min on a laptop CPU
- `--threshold 0.12` slide-change sensitivity. Raise (0.2-0.3) if there are too many
  near-duplicate frames (e.g. lecturer cam in shot), lower (0.06) if slides are being missed
- `--min-gap 8` minimum seconds between frames
- `--no-frames` audio-only lectures or when slides were shared separately

Transcription is slow, so run it in the background for long recordings and tell
the user roughly how long. Output dir is reused, so a re-run after a failure
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
