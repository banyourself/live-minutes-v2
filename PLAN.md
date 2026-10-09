# Live Zoom Minutes: Product Plan

Goal: software that reads a meeting as it happens and drafts minutes in each
organization's own template, usable by any school.

Status as of 2026-09-30 (evening): full product framework built and tested.
- Hosted multi-district server (FastAPI, PostgreSQL, worker queue, migrations): accounts,
  Google/Microsoft sign-in, districts and organizations, roles, invites, per-org AI keys
  (encrypted), templates, live meetings, capture tokens, Zoom per org, approval, Word and
  transcript exports (TXT/VTT/SRT), activity log.
- React web app, Windows desktop installer (Electron, built-in Zoom caption reader),
  Chrome extension for hosted servers, Docker/Compose/Render deployment, GitHub CI.
- Tested: 14 engine tests, 7 server tests (tenancy, roles, CSRF, key encryption, SSRF
  block, full capture-to-export flow), live browser walkthrough, desktop app launch.
- Not yet tested: a real Zoom meeting, a real AI provider, Google/Microsoft sign-in with
  real clients.

Update 2026-09-30 (night): security hardening done (step 1 of the roadmap below). Email
confirmation, password reset, shared sign-in limits, tenant-restricted SSO, CSP/HSTS, host
checks, size limits, pinned AI connections, rotatable keys, draft revision checks, a
hardened desktop app, hash-pinned dependencies, and security scans in CI. 22 server tests
and 16 engine tests pass on SQLite and PostgreSQL.

Update 2026-10-01: live pilot at https://minutes.kevinle.tech (Docker on Kevin's PC behind a
Cloudflare Tunnel, email through Resend, Cloudflare Turnstile on). Added school verification
(directory, student or staff email codes, join requests, college approvals), strict password and
email rules, a security assessment of the live site, the Platform dashboard, district and college
IT roles with an IT console, and a billing ledger. 39 server tests and 16 engine tests.

Update 2026-10-01: official directory (districts, colleges, and organizations only by approval,
look-alike detection, district merge), Student, Faculty, Staff, and IT accounts, and AI sharing.
Districts share AIs with colleges, colleges with organizations or people, and people can add their
own. Each task picks its AI and prompt (person, organization, college, district, then platform
default), every call is metered and priced, and organizations have monthly limits. 50 server tests.

Update 2026-10-01 (later): officer positions with ranks, permissions, and terms that end on their own,
permission editing for advisors and IT, and advisor review before approval. 55 server tests.

Update 2026-10-01 (evening): scheduled and recurring meetings with Zoom links, a month calendar,
calendar files and private calendar links, and captions that start a scheduled meeting. 62 server tests.

Update 2026-10-01: saved motions and votes per meeting, search with links to the source line, AI
questions with numbered citations, voting records per person, and funding requests linked to the
approving motion, with CSV exports. 67 server tests.

Update 2026-10-01 (later): plain-language summaries, translations with their own Word files, and an
accessibility check on every Word file, which now always carries a title and language. 70 server tests.

Update 2026-10-01 (evening): notifications in an inbox and by email, with reminders, review alerts, officer
changes, and a weekly summary, each switchable per person. 75 server tests.

Update 2026-10-01: school sign-in set by district IT with automatic account setup, a shared template
library for districts and colleges, and bulk invites from a list or CSV. 79 server tests.

Update 2026-10-01 (later): retention rules, legal holds that block every delete, and a full district or
college export as one ZIP. 82 server tests.

Update 2026-10-01 (evening): usage reports for districts, colleges, and the platform, and procurement
drafts (HECVAT Lite, accessibility report, FERPA agreement template, subprocessors). Every phase of the
2026-10-01 feature list is now live. 84 server tests.

Update 2026-10-01: weekly summary email is opt-in and a This week page shows it in the app; district and
college backup destinations with chosen data and schedules; nightly server backups; accessibility fixes
(skip link, page titles, focus outlines, contrast, status announcements, idle warning); privacy policy,
terms of use, accessibility statement, and recorded terms acceptance. 88 server tests.

Update 2026-10-01 (later): upload past meetings and import from Zoom share links, recordings that play beside a
following transcript, private and public meetings with public pages, example minutes for style, built-in starter
templates and defaults, and funding decisions that save only on Save. 92 server tests.

Update 2026-10-01 (night): MCP server for Claude Desktop and Claude Code with personal tokens, one-click
OpenRouter connect, clearer default AI labels, dollar amount fields, every meeting private until made
public, and examples that use no real member names. 95 server tests.

Update 2026-10-01 (late): chat assistant on every page with an AI use and limit meter. It answers questions and
suggests officer, position, meeting, invite, and role changes that run only after Approve, with the person's own
permissions and no deletions. 98 server tests.

Update 2026-10-01 (night): template designer with a live preview, Word download, and editing later; built-in
templates no longer repeat Call to Order and Adjournment. Security review fixes: school sign-in can no longer
attach to someone else's account through an unverified directory email, MCP tokens reach only real memberships
and save only meetings they just read, S3 backups go only to known storage hosts, recording uploads are capped,
public recordings are rate limited, sent emails drop their links, and failed sign-ins lock the attacker's
network instead of the account owner. 102 server tests.

Update 2026-10-01 (late night): draft history with GitHub-style comparisons and restore; OAuth sign-in so the
Claude website, desktop, phone, Claude Code, and ChatGPT connect to the MCP server without a token; a Recordings
page with single and ZIP downloads, and a ZIP of every recording for district and college IT. 108 server tests.

Update 2026-10-02: navigation redesign. Grouped sidebar with icons (Meetings, Records, Organization, Administration),
an account menu for My account, Customize, joining an organization, and signing out, a phone menu with a top bar and
notification bell, Settings tabs in order of use (General first) with links that remember the tab, My account split
into Profile, Notifications, and AI tabs, shorter meeting tabs that scroll on phones, Approve as the main action on
finished drafts, and new meetings that use the organization's default AI. 109 server tests.

Update 2026-10-02 (later): template designer with every label editable, alignment, fonts, colors, sizes, heading
styles, and numbering, and seven distinct built-in styles; student IDs with lookups for advisors, staff, and IT;
Claude and ChatGPT can suggest approval-gated changes through MCP when no in-app AI is set up. 112 server tests.

## Feature build order (2026-10-01)

Each phase is tested, deployed to minutes.kevinle.tech, and pushed before the next starts.

1. AI owners, sharing, tasks, prompts, metering, and limits. Done.
2. Officer positions with terms (fixed dates or permanent), editable position permissions
   (defaults: Advisor all, President assigns and removes, Vice President assigns only), and an
   advisor review step before approval. Done.
3. Scheduled and recurring meetings with Zoom links and a calendar feed. Done.
4. Search and AI questions across past minutes with links to the source, voting records per
   member with export, and funding requests linked to the approving motion. Done.
5. Translation, plain-language summaries, and accessibility checks on exports. Done.
6. Notifications: draft ready, approval needed, weekly digest. Done.
7. Shared template library per district, school sign-in with automatic account setup, bulk invites. Done.
8. Retention rules, legal holds, and a full district data export. Done.
9. Usage reports and procurement paperwork (HECVAT Lite, VPAT, FERPA templates). Done.

## Roadmap to a district handover (Zoom only)

Hosting: Microsoft Azure, because Coast District already signs everyone in through
Microsoft Entra. Pilot in Kevin's Azure for Students subscription at minutes.kevinle.tech;
handover is the district deploying the same template into its own subscription.

1. Security hardening. Done (plus school verification, roles, dashboards, billing ledger).
2. Azure hosting: Bicep template (Container Apps for web and worker, PostgreSQL Flexible
   Server, Blob Storage, Key Vault, Application Insights) on a private network, GitHub
   deploys with OIDC, staging and production, backups.
3. Accounts and email: optional two-step sign-in (done 2026-10-07: authenticator app, recovery codes,
   signed-in devices, security emails), a district "school SSO only" setting. AI connections can be
   edited (name, model, key, server) and link to each provider's key page (done 2026-10-07).
   Plans, not keys: each meeting links to Claude and ChatGPT with the drafting request filled in, using
   the Live Minutes connector (done 2026-10-07). Live Minutes never holds Claude or ChatGPT plan sign-ins:
   Anthropic forbids and blocks it. OpenAI's Sign in with ChatGPT can bill a ChatGPT plan, but a hosted
   app needs OpenAI's approval through its interest form first; build it only after approval.
4. Minutes features: draft history with restore, unresolved items carried to the next
   meeting, meeting rules (open-meeting law, Robert's or Rosenberg's, quorum, vote
   thresholds), retention auto-delete, schema-checked drafts with [verify] tracking,
   Gemini and Azure OpenAI providers with retries, a private quality check against the
   9/16, 9/23, 9/30 minutes that runs only on Kevin's computer.
5. Live and scale: pushed updates instead of polling, timed live drafts, worker
   autoscaling, load test.
   Also done 2026-10-07: unfinished business carried into new meetings, an opt-in public archive of
   approved minutes, optional Zoom auto-import when a cloud recording finishes, and encrypted offsite
   backups to Cloudflare R2 (running since 2026-10-07, with a 29-day bucket lock).
   Done 2026-10-08: a free AI built into the server (Ollama with a small open model) for every account, in
   its own drafting lane so it never slows paid AIs; minutes only, drafted after the meeting, about 15 to
   40 minutes per hour of meeting.
   Done 2026-10-07: sign-up asks Personal or School. Anyone can make a personal account and gets a
   private workspace once their email is confirmed (2 GB of recordings each, open sign-up can be
   turned off under Platform settings).
   Done 2026-10-07: the web app loads each page only when it is opened (the first download went
   from 637 KB to 319 KB before compression), common pages prefetch after the app loads, and
   fingerprinted files are cached for a year.
6. Zoom: one Live Minutes app for everyone, user-managed, with connect from Settings or the
   Marketplace, signed `app_deauthorized` handling, and personal workspaces by invitation (done
   2026-10-07; the development app is connected and tested, listing text, icons, cover, and screenshots
   are in docs/zoom-listing, and Marketplace submission is next, see docs/ZOOM-APP-SETUP.md). Still to do: automatic
   transcript import when a recording finishes (signed webhook) and RTMS live mode behind a switch.
   Also done 2026-10-07: imports prefer Zoom's saved closed captions, shared Zoom accounts are told
   apart from context, and reference transcripts from Otter and similar apps check names, numbers,
   motions, and votes. A "Connect Fathom" button (Fathom offers OAuth apps) could feed references
   automatically later.
7. Desktop and extension: signed installer (Azure Artifact Signing), auto-update from the
   district's own server, extension by district policy or unlisted Web Store listing.
8. MCP connector that runs on the user's own computer with a personal token.
9. Handover package: one-command deploy, admin guide, runbook, threat model, HECVAT Lite,
   accessibility check for a VPAT, FERPA statement, full security scan and outside test.

Kevin's steps: activate Azure for Students, add a DNS record for minutes.kevinle.tech,
get an AI key, and later the code-signing identity check and Zoom developer app. I own the
code; any license for district use is a separate agreement.

---

## 1. Getting live captions

| Option | How | Speaker names | Needs admin/IT |
|---|---|---|---|
| **A. Zoom web client + page script** (start here) | Join from app.zoom.us in Chrome; a small script watches the caption/transcript elements and streams each line to a local program | Yes | No |
| B. Windows UI Automation | Read the desktop app's transcript panel through the accessibility layer | Yes, if Zoom exposes it (untested) | No |
| C. Screen OCR (Cluely-style) | Screenshot the caption area, OCR, de-duplicate | Only if the transcript panel is visible | No |
| D. RTMS (official) | Zoom streams transcripts to our server over WebSocket | Yes | Yes: Marketplace app, admin approval, public HTTPS server |
| E. System audio + our own speech-to-text | Transcribe the audio ourselves | Weak (diarization) | No |

Notes:
- The Zoom Closed Caption API only accepts captions into a meeting. It cannot read them.
- Live captions must be enabled by the ASG host account. Recording
  transcripts are a separate setting.
- The ASG advisor offered (9/30) to make Kevin an alternate host. Test at the next meeting.
- Do not copy Cluely's "invisible to others" design. Public meetings need transparency.

**Access without being host.** API and RTMS permission comes from the account that
owns the meeting, not from meeting roles. Two routes:
1. Host shares the recording link or downloaded .vtt after each meeting (works today;
   used for 9/23). No approvals, but manual.
2. Host account authorizes the app once (recommended automated route): district IT
   allows the app on the CCCD Zoom account and enables RTMS for it; whoever controls
   The ASG host account clicks "Allow" once. The app then pulls recordings after each
   meeting and receives live transcripts via RTMS (set to auto-start) on the host's
   behalf. Kevin never needs to be host.

## 2. Real-time pipeline

1. Load the agenda slots from the template (`inspect`).
2. Stream caption lines into a running transcript, including the Zoom chat.
3. Every minute or two, or on topic change, send new lines to the LLM to update `minutes.json`.
4. Motion tracker: detect "motion", "second", "roll call", "abstain" and show
   "X moved / Y seconded / vote pending" on a local page so the secretary can fix it live.
5. At adjournment, run `fill` to produce the .docx draft.

## 3. Lessons from real meetings (9/23, 9/30)

- Shared room account ("Coastline ASG") carries several speakers. Needs roster aliases plus
  context rules (the chair calling on a speaker by name).
- Votes and reports come through chat. Chat must be read.
- Items are taken out of order and moved to later meetings. Match by topic, not order.
- Unresolved questions (for example a funding amount left open) should carry forward to the next agenda.
- Style: ONE condensed bullet per topic, 9/16 minutes tone, end with the action taken.
- Caption spellings of names are unreliable (one person can be spelled several ways in one meeting). Flag with [verify].
- Agenda list numbering differs in every file. Detect from numbering.xml (done 9/30).

## 4. Architecture

- Transcript sources: upload/paste, Zoom recording webhook, live captions (option A), RTMS later, Teams/Meet, in-person audio.
- Drafting engine: transcript + agenda -> structured minutes via LLM, with [verify] flags linked to timestamps.
- Templates: each organization uploads its .docx agenda; `fill` renders it.
- Review web app: approve, edit, export, live motion tracker.
- Accounts: organizations, roles (secretary, advisor, member), school SSO, version history.
- Stack: Python backend (reuse current code), Postgres, job queue, React frontend.

## 5. AI providers and sign-in

- Adapter layer from day one: Claude, OpenAI, Gemini, and any OpenAI-compatible
  endpoint (OpenRouter, Groq, Grok, LM Studio, Ollama, vLLM). Validate output against
  the minutes schema and retry.
- "Login with Claude" using a Pro/Max plan: not allowed for third-party apps (Anthropic terms).
- "Sign in with ChatGPT": launched 2026-09-29, limited to select partners. Join the waitlist.
- Available now: MCP connector (use it from Claude/ChatGPT with your own plan),
  OpenRouter sign-in, bring your own API key, local models.
- Higgsfield does not apply (image/video generation, not text).

## 6. Multi-school requirements

- Tenant isolation from day one.
- Configurable open-meeting rules (Brown Act is California only) and parliamentary rules.
- Procurement: HECVAT, FERPA data agreement, VPAT (accessibility), later SOC 2.
- Accessible exports (ADA/508), approval workflow and audit trail, retention settings.
- Pricing: free tier with own key, per-school or per-district plans.

## 7. Phases

1. Drafting engine (CLI): adapter layer, roster aliases, chat ingestion, motion checks,
   eval set from the 9/16, 9/23, 9/30 minutes. Test on ASG.
2. Live capture prototype (option A) + motion tracker page.
3. Pilot with 2 to 3 other schools.
4. Web app, Zoom Marketplace app, Teams app, compliance paperwork.
5. RTMS live mode and MCP server.

## 8. Open questions

- Does the Zoom web client show captions to non-hosts in this meeting setup? Test once.
- Is Zoom exposing transcript text to Windows UI Automation? Test once.
- District/advisor approval for sending meeting data to an outside AI service.
- Which AI provider first (needs Kevin's own API key in `.env`).

Update 2026-10-02 (evening): removed student IDs (the column and any saved IDs are dropped) and public meetings.
Every meeting and recording is private to members and the staff who manage them; the public pages and API are gone.
111 server tests.

Update 2026-10-04: access levels renamed (Full access, Runs meetings, Member, Read only); Advisor and President give
full access; only college and district IT create and delete organizations, with settings to allow faculty and staff
to create them and positions with the new Delete permission to delete them. AI hardening against the OWASP Top 10 for
LLM applications, smaller prompts, prompt caching for Claude, and docs/AI-REFERENCE.md for AIs. 116 server tests.


Update 2026-10-04 (evening): sample meetings choose a length (about 15, 45, or 90 minutes, a mix, or 10 to 120
minutes) and never repeat. The live pilot moved from Kevin's PC to an Oracle Cloud Always Free Ampere VM (Phoenix,
4 OCPUs, 24 GB) with the same Compose stack and tunnel; deploy/oracle has the setup, move, and update scripts.
Development continues in banyourself/live-minutes-v2.

Update 2026-10-05: select and delete meetings from the minutes list (Full access, blocked by legal holds). Security
review fixes: school sign-in only marks an email verified when it is the same address the school vouched for; officers
with full access can't remove someone ranked at or above them or make themselves permanent owners; AI usage is only
shown for an organization, college, district, or the platform; changing an AI's server address needs its key again;
legal holds also stop replacing recordings, removing motions, funding requests, and translations, and pruning draft
history; recordings exports escape spreadsheet formulas; uploads are capped per organization; password resets and
disabled accounts revoke app, calendar, and capture tokens; college IT can't reset or unlock district IT or the platform
owner. Bug fixes: sample meetings no longer send reminders, appear in This week, or show up in the capture apps; missed
scheduled meetings leave Upcoming; read-only members no longer see actions they can't use; exports stop if saving the
draft fails; non-English titles download correctly. 120 server tests.

Update 2026-10-05 (later): sample meetings reach the chosen length even when the template has only one or two items
(the generator adds its own reports and new business, then fills any time left with other business), and no sentence
pattern repeats in a meeting unless it is about a different event, issue, office, or committee; vote lines name the
motion. Password reset and email confirmation links, administrator reset links, school email codes, the password
confirmation window, and sign-in handoffs now last 10 minutes. Second security review fixes: invite sign-ups still
confirm their email; confirming an email needs the sign-up password; only owners and IT invite owners; password changes
revoke app, calendar, and capture tokens; school-sign-in-only accounts set a password by emailed link; school sign-in
clears passwords on accounts never confirmed by email; reused OAuth refresh tokens disconnect the app; with Turnstile on,
failed sign-ins no longer lock the account for everyone; owners can manage co-owners but not the advisor. 124 server tests.
