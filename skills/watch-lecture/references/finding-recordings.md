# Finding a recording in the browser

Use this when the user names a lecture ("COSC121 week 4 lecture 2", "yesterday's
INFO213 lecture", "all of last week's MATH102 lectures") instead of giving a file
or URL. It drives the user's own browser, where they're already signed in to Learn
and Echo360.

## Which browser tool

Use whichever is available, in this order:
1. **Claude in Chrome** (`mcp__claude-in-chrome__*`). Best option because it has the
   user's real UC sign-in and can read network requests. If its tools are deferred,
   load them in one ToolSearch call:
   `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__tabs_close_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__find,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_network_requests,mcp__claude-in-chrome__javascript_tool`
2. The desktop app's built-in browser (`mcp__Claude_Browser__*`). The user may need to
   sign in there once.
3. Neither available: tell the user to install/connect Claude in Chrome, or fall back to
   asking them for the file/URL (see the table in SKILL.md).

Load the matching browser skill (`chrome-browser` / `built-in-browser`) if one is listed.

## Steps

1. **Pin down which lecture.** Course code plus week/date/topic. Ask only if it's
   genuinely ambiguous. Today's date is in context, so "yesterday" or "last week" can
   be worked out.
2. **Open a new tab** (don't hijack the user's tabs) and go to the course on Learn:
   `https://learn.canterbury.ac.nz/my/courses.php`, then open the course. For other
   unis, use their LMS (Moodle/Canvas/Blackboard) the same way.
3. **Never type the user's password or handle MFA.** If a login page appears, ask the
   user to sign in in that tab, wait for them to confirm, then carry on.
4. **Find the Echo360 link.** Usually a block or activity called "Echo360", "Lecture
   recordings", "Echo360 Recordings" or similar, sometimes inside the first section or a
   "Lecture recordings" topic. It's an LTI launch, so it may open in a new tab or an
   iframe. If it's an iframe, read the iframe's `src` and navigate the tab to it directly.
5. **Find the lesson.** The Echo360 course page (`echo360.org.au/section/<id>/home` for
   NZ/AU) lists recordings by date and title. Use `read_page` / `find` rather than
   screenshots where possible. Match on date first, titles are often just the course code.
   Confirm with the user if two recordings plausibly match (e.g. a re-recorded lecture).
6. **Get the media**, trying these in order and stopping at the first that works:

   a. **Captions/transcript.** Open the lesson, open the Transcript/Captions panel, then
      `read_network_requests` and look for URLs containing `vtt`, `srt`, `caption` or
      `transcript`. Fetch it with `javascript_tool`
      (`await (await fetch(url, {credentials:'include'})).text()`), then save the text as
      `captions.vtt` in the output dir. Captions skip Whisper entirely, so always try for
      them, even when you'll also get the video for slides.

   b. **Download.** The lesson's `...` / menu → *Download* (only shown if the lecturer
      enabled it). Pick the SD video with slides (HD isn't needed, frames get scaled
      to 1280px anyway). The file lands in the user's Downloads folder. In a sandbox,
      that folder must be shared with you before the script can read it.

   c. **Stream URL.** Open the lesson player and press play, then
      `read_network_requests` filtered for `m3u8`. Take the **master** playlist (usually
      the first `.m3u8` requested, on `content.echo360.org.au`), with its full signed query
      string. If there are separate streams for the screen and the lecturer camera (often
      `s1...` and `s2...`), use the screen one for slides; the audio is usually on it too.
      If unsure, grab a single frame of each with ffmpeg and look. Pause the video after.
      Signed URLs expire after a few hours, so run the script straight away.
      If the script gets a 403 on the stream, Echo360 is using signed cookies rather than
      a signed URL: add `--cookies-from-browser chrome` (only works when running natively on
      the user's machine, not in a sandbox). Otherwise fall back to (a) or (b).

7. **Close the tabs you opened** and run `process_lecture.py` with what you got
   (`--captions captions.vtt` plus the video/stream for slides). Use the course code and
   date in `--title`, e.g. `"COSC121 2026-10-14 Lecture"`.

## Several lectures at once

For "all week 3 lectures" etc., collect every lesson's media first (stream URLs expire,
so don't browse for an hour then process), then run the script on each one. Run them
in the background one after another, since Whisper uses all CPU cores anyway.

## Staying in bounds

- Only look at the course and lesson needed. Don't open other courses, grades,
  messages or assignments.
- Don't click anything that changes state (submit, delete, mark complete, post).
- If Echo360's layout doesn't match these steps, describe what you see to the user
  and ask, instead of clicking around blindly. After 2-3 failed attempts at a step,
  stop and fall back to asking the user for the file or URL.
