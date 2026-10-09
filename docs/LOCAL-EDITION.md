# Local edition and command-line tool

Live Minutes started as a command-line tool and a single-user app that run on one computer. Both still ship in this repository and share the minutes engine with the hosted edition. The project overview is in the [README](../README.md).

---

# Local single-user edition

Turns a meeting into filled-in minutes. Upload an agenda, a minutes template, or just a
list of topics; connect any AI; feed it the meeting (live captions, a Zoom transcript,
or the chat); get a Word draft in your own format, live or after the meeting.

**Everything runs on your computer.** The secretary reviews every draft. See
[docs/IT-REVIEW.md](IT-REVIEW.md) for what is and isn't sent anywhere, and
[PLAN.md](../PLAN.md) for the roadmap.

## Quick start

```bash
cp .env.example .env        # add the API key for the AI you use (or use a local model)
python run_app.py           # then open http://127.0.0.1:8765
```

1. **Notes document**: upload a .docx template/agenda (its format is kept) or a
   .txt/.pdf/.docx list of topics (a clean template is generated). Choose Live or After.
2. **AI connection**: pick a provider and type a model name. Keys stay in `.env`.
   Supported: Claude (API key), OpenAI, OpenRouter, Groq, Grok (xAI), Hugging Face, LM Studio,
   Ollama, any OpenAI-compatible server. PDF uploads need `pip install pypdf`.
3. **Meeting sources**, one or several at once:
   - **Live captions**: load `capture-extension/` in Chrome (chrome://extensions,
     Developer mode, Load unpacked), paste the capture token into its options, join
     from the Zoom web client, open the transcript panel, click "Pick captions area".
   - **Import**: a Zoom `.vtt`, a chat file, or text copied from a recording page.
   - **Zoom**: the account that hosts the meetings connects once, from Settings or from
     the Zoom App Marketplace; then import recordings with their closed captions (or audio
     transcript) and chat. Removing the app in Zoom disconnects it here too. See [docs/ZOOM-APP-SETUP.md](ZOOM-APP-SETUP.md)
     and the public help page at /help/zoom.
4. Watch the draft and the **motion tracker** update, fix anything live, then
   **Finish & build Word file**.

Tests (no API key needed; a fake AI server stands in):

```bash
python -m unittest discover -s tests -v
```

## Project layout

| Path | What |
|---|---|
| `run_app.py`, `minutes_app/` | The local web app: sessions, transcript merging, motion tracker, AI drafting |
| `capture-extension/` | Chrome extension that reads the Zoom web client's caption panel |
| `zoom_minutes.py` | Template engine and the original command-line tool (below) |
| `docs/` | IT review packet, Zoom app setup |
| `tests/` | Offline test suite |

---

# Command-line tool: `zoom_minutes.py`


Turns a Zoom meeting transcript into a filled-in ASG minutes document, keeping the
template's Word styles, bullet numbering and indentation exactly as they are.

Python 3.8+. **Standard library only** - nothing to `pip install`.

There are two ways in. Start with the manual one; it needs no permissions from anybody.

---

## Path A - manual transcript (works today, no credentials)

You need no Zoom app, no admin, no API access.

1. Open the recording on `cccd-edu.zoom.us` and sign in.
2. Find the **Audio Transcript** for the meeting and download the `.vtt`.
   (If there is no Audio Transcript, transcription was off for that recording -
   see *Transcripts only exist if* below.)
3. Turn it into a readable, speaker-labelled transcript:

```bash
python zoom_minutes.py local --vtt "ASG 2026-09-30.vtt" --date 2026-09-30
```

That writes `ASG 2026-09-30.txt`, which opens with a speaker roster:

```
#   Kevin                22.4 min   0:00:04 -> 1:58:12   84 turns
#   Alex Rivera          14.1 min   0:03:30 -> 1:57:40   52 turns
```

The roster is worth reading before anything else - it cross-checks roll call and
catches late arrivals, since the *first heard* column shows when each officer
actually started speaking.

4. Hand that `.txt` to Claude along with the meeting's agenda `.docx`, and ask for a
   `minutes.json`. Then jump to **Filling the template** below.

---

## Path B - automated pull from the Zoom API

This one needs a **Server-to-Server OAuth app** on the CCCD Zoom tenant, which
requires Marketplace-app privileges - an admin role. A student officer account will
not have it. District IT has to create the app, or grant the role.

### What to ask district IT for

> A Server-to-Server OAuth app on the CCCD Zoom account, with read access to cloud
> recordings and their transcripts, for pulling ASG meeting transcripts into the
> minutes. I need the Account ID, Client ID and Client Secret.
>
> Scopes: the read scopes for cloud recordings. Depending on how the account is
> configured these appear either as the classic `recording:read:admin`, or as the
> granular `cloud_recording:read:list_user_recordings:admin` and
> `cloud_recording:read:list_recording_files:admin`. Optionally
> `meeting:read:summary:admin` if we also want AI Companion summaries.
>
> If ASG meetings are hosted under a staff account rather than mine, the app needs
> the admin-level variants so it can read that host's recordings.

### Configure

Copy `.env.example` to `.env`, fill it in, and keep it out of anywhere shared:

```bash
cp .env.example .env
```

`.env` holds a client secret. Treat it like a password - don't commit it, don't put
it in a shared drive. The script also caches an access token in `.zoom_token.json`
(chmod 600 where the OS supports it); that file is equally sensitive and is safe to
delete at any time.

### Use

```bash
python zoom_minutes.py auth-check                    # confirm credentials work
python zoom_minutes.py list --days 14                # what recordings exist
python zoom_minutes.py fetch --date 2026-09-30 --out transcript.txt
```

`list` shows a `vtt` column - `NO` means that recording has no transcript to fetch.

Set `ASG_MEETING_ID` in `.env` (digits only, e.g. `12345678901`) and both commands
filter to the ASG meeting automatically.

---

## Filling the template

Independent of how you got the transcript.

See what the agenda document exposes as fillable, and get a starter JSON:

```bash
python zoom_minutes.py inspect --template "ASG 2026.09.30 Minutes.docx" \
    --skeleton minutes.json
```

`inspect` marks each slot: `ITEM` an agenda item you can attach discussion to,
`EMPTY` a blank bullet waiting for text, `BLANK` a `____ moved to …` placeholder.

Then apply a filled-in JSON:

```bash
python zoom_minutes.py fill --template "ASG 2026.09.30 Minutes.docx" \
    --data minutes.json --out "ASG 2026.09.30 Minutes DRAFT.docx"
```

It prints every change it made, and every key that matched nothing:

```
applied 17 change(s):
  + call to order  [replaced]
  + motion under 'moved to create a task force'  [replaced placeholder]
  ...
SKIPPED 1 -- these did not match the template:
  ! discussion under 'Bylaws Subcommitee'  [no agenda item matching ...]
```

Anything under `SKIPPED` was silently *not* written, and `fill` exits non-zero when
that happens. Skips are almost always a typo in an `under` key - matching ignores
case, spacing and punctuation, but not misspellings.

### minutes.json

```jsonc
{
  "order_time": "9:04 a.m.",
  "adjourn_time": "11:02 a.m.",

  // Appended to the roll call line that contains this text.
  "roll_call": {
    "Secretary - Kevin": "Present (9:15)",
    "Legislative Affairs Commissioner": "Absent"
  },

  // Replaces a "____ moved to ..." placeholder, or adds a bullet if there is none.
  "motions": [
    { "under": "moved to create a task force",
      "text": "Kevin moved to create a task force ... Motion passed unanimously." }
  ],

  // Discussion summary, into the bullet under the matching agenda item.
  "fills": [
    { "under": "Hope Scholars Appointment Preparation", "text": "Kevin ..." }
  ],

  // Officer / advisor reports. Searched only below the REPORTS heading, so
  // "President - Alex" cannot collide with the roll call line of the same name.
  // A plain string is joined with " - ". An object with "sep": " " reads
  // "President - Alex reported on ...", the style of the 9/16 minutes.
  "reports": {
    "President - Alex": { "sep": " ", "text": "reported on ..." },
    "Secretary - Kevin": "N/A"
  },

  // Bold bullets under "Key Items Discussed/Actions Taken".
  "summary": [
    "Community Service Task Force Approved: Passed unanimously to ..."
  ],

  // Typos carried over from the agenda. whole_paragraph only replaces a
  // paragraph whose entire text matches.
  "corrections": [
    { "find": "Kevan", "replace": "Kevin" },
    { "find": "Hope Scholar", "replace": "Hope Scholars Senator", "whole_paragraph": true }
  ]
}
```

`under` and the `roll_call` / `reports` keys are **substring** matches against the
paragraph text, normalised for case, spacing and punctuation. Use enough of the line
to be unambiguous - `"Bylaws"` matches several paragraphs, `"Bylaws: (Kevin) will
provide an overview"` matches one.

---

## Things that will bite you

**Transcripts only exist if** the meeting was **cloud**-recorded *and* audio
transcription was enabled before it started. Local recordings never reach the API,
and a cloud recording made with transcription off has no VTT to download - after the
fact there is no way to generate one. Check this once, in Zoom settings, and it stops
being a problem.

**Zoom needs time after the meeting.** The transcript is not ready the moment you
adjourn; processing typically takes a while for a two-hour meeting.

**Zoom mishears names and motion language.** It will render `NTE` as `NTU`, mangle
surnames, and lose who seconded a motion when two people speak at once. The draft is
a draft.

**Every output is a draft.** For a Brown Act body the minutes are the official
record, the secretary owns them, and ASG adopts them by motion at the next meeting.
Read the draft against the recording before it goes to the board.

---

## Commands

| Command | Needs Zoom API | Does |
|---|---|---|
| `auth-check` | yes | Verify credentials and show who you authenticated as |
| `list` | yes | List cloud recordings, flagging which have transcripts |
| `fetch` | yes | Download and parse a transcript |
| `local` | no | Parse a `.vtt` you downloaded by hand |
| `inspect` | no | Show a template's fillable slots; write a starter JSON |
| `fill` | no | Apply a minutes JSON to a template |
