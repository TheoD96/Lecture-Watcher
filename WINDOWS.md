# Lecture Watcher on Windows: step by step

This takes a fresh Windows 10/11 PC to "Claude, make notes from this lecture" in about
20 minutes. Most of that is downloads.

You'll type commands into **PowerShell**. Open it with Start → type `PowerShell` → Enter.
After any step that installs something, **close PowerShell and open a new one** so it
picks up the new programs.

---

## Step 1. Install Git for Windows

Claude Code needs it on Windows (it runs commands through Git Bash).

```powershell
winget install --id Git.Git -e
```

Accept the prompts. If `winget` isn't recognised, install **App Installer** from the
Microsoft Store first, or download Git from https://git-scm.com/download/win and click
through the installer with the defaults.

Check (in a new PowerShell):

```powershell
git --version
```

## Step 2. Install Python

```powershell
winget install --id Python.Python.3.12 -e
```

(Or use the installer from https://python.org and tick **Add python.exe to PATH** on the
first screen.)

Then turn off the fake "python" that opens the Microsoft Store:

1. Settings → Apps → Advanced app settings → **App execution aliases**
2. Turn **off** both *python.exe* and *python3.exe* (App Installer)

Check:

```powershell
py --version
```

You should see `Python 3.12.x`.

## Step 3. Install ffmpeg (optional, recommended)

The Python packages include their own ffmpeg, so this is optional, but a system one is
handy and usually newer.

```powershell
winget install --id Gyan.FFmpeg -e
```

Check (new PowerShell): `ffmpeg -version`

## Step 4. Install the Python packages

```powershell
py -m pip install --upgrade pip
py -m pip install "faster-whisper>=1.0" numpy Pillow yt-dlp imageio-ffmpeg
```

Check:

```powershell
py -c "import faster_whisper, yt_dlp, imageio_ffmpeg, PIL; print('ok')"
```

It should print `ok`. If pip prints warnings about scripts not being on PATH, ignore them,
the plugin doesn't need it.

## Step 5. Install Claude Code

```powershell
irm https://claude.ai/install.ps1 | iex
```

Then open a new PowerShell and run:

```powershell
claude
```

Follow the prompts to log in with your Claude account (Pro or Max plan, or an API key).
Type `/exit` to quit it for now.

Prefer a GUI? The Claude desktop app and the VS Code extension work too; the plugin
steps below are the same.

## Step 6. Give Git access to the repo

The repo is private, so Git needs to be logged in to a GitHub account that can see it.

```powershell
winget install --id GitHub.cli -e
```

New PowerShell:

```powershell
gh auth login
```

Pick **GitHub.com → HTTPS → Yes (authenticate Git) → Login with a web browser**, and
finish in the browser.

(Skip this step if the repo has been made public.)

## Step 7. Install the plugin

Start Claude Code in a folder where you want the lecture notes to go, e.g.:

```powershell
mkdir $HOME\Lectures
cd $HOME\Lectures
claude
```

Inside Claude Code, run these two commands:

```
/plugin marketplace add theod96/lecture-watcher
/plugin install lecture-watcher@lecture-watcher
```

Then restart Claude Code (`/exit`, then `claude` again). Check it's there:

```
/plugin
```

`lecture-watcher` should be listed as installed.

## Step 8. (Optional) Let Claude find lectures for you

To say things like "watch COSC121 week 4 lecture 2" and have Claude find the recording
on Learn/Echo360 itself, install the **Claude in Chrome** extension from the Chrome Web
Store, sign in with the same Claude account, and stay logged in to Learn in Chrome.

Without it, you just give Claude the file, captions, or stream link yourself (step 10).

## Step 9. (Optional) NVIDIA graphics card

Out of the box, transcription runs on the CPU: very roughly 15 to 30 minutes per hour
of lecture with the default `small` model. If you have an NVIDIA GPU, it can be much
faster:

```powershell
py -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

If you ever see an error mentioning `cudnn` or `cublas`, either install those or tell
Claude to "use --device cpu".

No NVIDIA card? Skip this, nothing to do.

## Step 10. Watch your first lecture

In Claude Code (started in your `Lectures` folder), just ask:

> make notes from this lecture C:\Users\you\Downloads\COSC121_wk4.mp4

> here's the captions file, summarise the lecture: C:\Users\you\Downloads\lecture.vtt

> watch COSC121 week 4 lecture 2 and quiz me on it *(needs step 8)*

Claude will ask permission before running commands; allow them. The first run also
downloads the Whisper speech model (about 500 MB), so it's slower than later runs.

Results land in `Lectures\lectures\<lecture name>\`:

| File | What it is |
|---|---|
| `notes.md` | Claude's study notes |
| `index.md` | Each slide next to what was said while it was up |
| `transcript.md` | Full timestamped transcript |
| `frames\` | One image per slide |
| `source.mp4` | The downloaded video. Safe to delete once you have notes |

### Getting the recording out of Echo360

Fastest first:

1. **Captions**: if the lesson has a transcript, download the `.vtt`. No Whisper needed,
   takes seconds.
2. **Download**: the lesson's `...` menu → *Download original* (only if the lecturer
   allows it).
3. **Stream link**: open the lesson in Chrome, press F12 → **Network** tab, type `m3u8`
   in the filter box, press play, right-click the first result → Copy → Copy URL. Give
   that whole link to Claude. It expires after a few hours.
4. **Needs your login**: on Windows, Chrome's cookies can't be read by other apps, so
   tell Claude to use **Firefox** cookies (be logged in to Echo360 in Firefox), or export
   a `cookies.txt` with a "Get cookies.txt LOCALLY" browser extension and give Claude its
   path.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `winget` not recognised | Install *App Installer* from the Microsoft Store |
| `py` / `python` not recognised | Reinstall Python and tick *Add python.exe to PATH*, then open a new PowerShell |
| `python3` opens the Microsoft Store | Turn off the aliases in step 2. Claude will also fall back to `py` |
| `claude` not recognised | Open a new PowerShell. Still missing? Re-run the step 5 install |
| Claude Code says Git Bash is required | Do step 1, then open a new PowerShell |
| `/plugin marketplace add` fails with "repository not found" or asks for a password | Do step 6 (`gh auth login`), or ask for access to the repo |
| `faster-whisper not installed` | Re-run step 4. If you have several Pythons, use `py -m pip ...` exactly as written |
| Error mentioning `cudnn` / `cublas` / `CUDA` | Step 9, or ask Claude to rerun with `--device cpu` |
| Hugging Face warning about symlinks | Harmless. Turning on Developer Mode (Settings → System → For developers) silences it |
| `403 Forbidden` on an Echo360 stream | The link expired or needs your login. Get a fresh link, or use Firefox cookies / `cookies.txt` (step 10, option 4) |
| `could not copy Chrome cookie database` / `failed to decrypt` | Expected on Windows. Use Firefox or `cookies.txt` instead of Chrome |
| Lots of near-duplicate slide images | Ask Claude to rerun with `--threshold 0.25` (lecturer camera in shot) |
| Slides being missed | Ask Claude to rerun with `--threshold 0.06` |
| Transcript gets jargon wrong | Ask Claude to use `--model medium` (slower, more accurate) |

## Updating

Inside Claude Code:

```
/plugin marketplace update lecture-watcher
```

then restart Claude Code. To update the Python packages:

```powershell
py -m pip install --upgrade faster-whisper yt-dlp imageio-ffmpeg
```

Keeping `yt-dlp` up to date fixes most "download suddenly stopped working" problems.

---

For personal study only. Don't redistribute lecture recordings.
