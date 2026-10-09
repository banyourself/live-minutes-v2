# Live Minutes architecture

```
 Zoom web client ──captions──▶ Desktop app (Electron)  ─┐
 (participant view)            or Chrome extension      │  HTTPS + capture token
                                                        ▼
 Browser / desktop window ──cookie session──▶  Web/API server (FastAPI)  ──▶ PostgreSQL
   React app (web/)                              │        ▲                  (orgs, users,
                                                 │ jobs   │ drafts           meetings, lines,
                                                 ▼        │                  audit log)
 Zoom API (optional, host-authorized) ◀──── Worker(s) ────┘ ──▶ File storage (volume or S3)
                                                 │                (templates, Word exports)
                                                 ▼
                                   AI provider chosen by each organization
                       (Claude, OpenAI, OpenRouter, Groq, xAI, Hugging Face, campus model, local model)
```

## Pieces

| Path | Role |
|---|---|
| `web/` | React + TypeScript single-page app. Built to `web/dist` and served by the API server. |
| `server/app/` | FastAPI API: accounts, districts and organizations, roles, AI connections, templates, meetings, capture, Zoom, audit. |
| `server/worker.py` | Drafting worker. Claims jobs from the database and calls the organization's AI. Run as many as needed. |
| `minutes_app/`, `zoom_minutes.py` | The minutes engine shared by every edition: template detection, transcript merging, motion tracker, AI drafting, Word fill. |
| `desktop/` | Electron app. Opens the organization's server, plus a Zoom window with a built-in caption reader. Builds a Windows installer. |
| `capture-extension/` | Chrome extension with the same caption reader, for people who join Zoom in Chrome. |
| `server/migrations/` | Alembic database migrations. |

## Tenancy and roles

District → organization (one school club, student government, board...) → members.
Every API call that reads or changes data checks membership in the owning organization;
users outside it get "not found". Roles, lowest to highest:

| Role | Can |
|---|---|
| viewer | read meetings and minutes |
| member | also create capture tokens, send captions, download files |
| secretary | also run meetings, import transcripts, edit and approve drafts, manage AI connections and templates |
| owner | also manage members, invites, organization settings, sign-in domains, delete meetings, read the activity log |

Platform administrators are listed by email in `PLATFORM_ADMIN_EMAILS`.

## Live meeting flow

1. A secretary creates a meeting from a template and an AI connection.
2. The desktop app or extension reads the caption panel and posts full snapshots every
   1.5 s with a capture token. The server diffs each snapshot against the stored tail,
   so scrolling and growing captions become clean, deduplicated lines.
3. When `LIVE_LINES` new lines arrive, or `LIVE_SECONDS` pass with any new lines, the
   server queues one drafting job per meeting (never more than one queued or running).
4. A worker drafts with the organization's AI, passing the current draft so the
   secretary's edits are kept, and validates every key against the real template.
5. The browser polls `/live` every 2.5 s for new lines, motions, and the draft. If the
   secretary is mid-edit, the new AI version is offered instead of overwriting.
6. End meeting queues a final full-transcript draft. Approve locks the draft. Export
   fills the organization's own Word template.

Imports (Zoom .vtt, chat files, recording-page text, or the optional Zoom connection)
merge into the same timeline by timestamp, so several sources can feed one meeting.

## Security model

See [SECURITY.md](../SECURITY.md) for the full list and how to report a problem.

- Accounts: scrypt passwords; every address is confirmed by an emailed link, an invite
  link, or school SSO before the account can do anything. Platform administrator rights
  are granted only after that confirmation, or by `python -m server.manage make-admin`.
- Sign-in limits are stored in the database, so they hold across replicas. Per account:
  5 failures in 15 minutes pauses sign-in and emails the owner, and 20 in a day locks it
  until a password reset. Per network: 30 failures or 120 attempts in 10 minutes, set high
  enough for a campus that shares one IP. Optional Cloudflare Turnstile adds a bot check.
  Unknown emails cost the same time as known ones. Forgot password and sign-up never
  reveal whether an account exists.
- Passwords: 12 or more characters with three kinds of characters (or a 20+ character
  passphrase), no common words or years at their core, no runs or repeats, no name or
  email, and not found in Have I Been Pwned. Emails are validated strictly, checked for a
  mail server, and disposable domains are refused.
- Schools: an account may use any email, but creating or joining an organization needs a
  school email confirmed by a 6-digit code (15 minutes, 5 tries) on a domain the directory
  lists for that school. One school email belongs to one account. Joining needs an
  owner's approval, and unlisted schools need the platform administrator's.
- Sessions: random tokens stored hashed in `__Host-` cookies (HttpOnly, Secure,
  SameSite=Lax). They end after 12 idle hours or 14 days, and a password reset or
  change signs out every other device.
- SSO: Microsoft sign-in accepts only the directory tenants in
  `MICROSOFT_ALLOWED_TENANTS` plus the tenants district IT enters in the IT console, and links
  accounts by tenant and object ID; Google can be limited to Workspace domains. A tenant or
  Workspace domain can belong to only one district. When automatic setup is on, a first sign-in
  from that directory creates the account and confirms the school email only if its domain is one
  of that district's college domains. An unconfirmed password account with the same email
  loses its password when the real owner signs in with SSO.
- CSRF: every state-changing `/api/` request must send `X-Live-Minutes: 1`, which a
  cross-site form cannot do; capture endpoints use tokens instead of cookies.
- Headers: strict Content-Security-Policy, HSTS, frame denial, no API docs in production,
  and the app answers only to the `PUBLIC_URL` host.
- Client IP comes from `X-Forwarded-For` only through `TRUSTED_PROXY_HOPS` proxies.
- Secrets at rest: AI keys and Zoom tokens are encrypted with `ENCRYPTION_KEYS`
  (rotatable). Capture tokens, invite links, and email links are stored only as hashes
  and expire.
- Outbound AI calls: the host must resolve only to public addresses, the connection is
  pinned to the address that was checked, and redirects are never followed, unless the
  deployment sets `ALLOW_PRIVATE_LLM_URLS=1` for a campus-hosted model.
- Requests are size-limited before they are read (1 MB, 2 MB for captions, 16 MB for
  uploads). Word files are checked for zip bombs and parsed without DTDs or entities.
- Drafts carry a revision number. An AI run never overwrites edits saved while it ran,
  and never touches approved minutes.
- Audit log of sign-ins, failed sign-ins, membership changes, AI and Zoom connections,
  imports, edits, approvals, exports and deletions.

## Scaling

- The API is stateless apart from small per-process caches; run several replicas
  behind a load balancer (`WEB_CONCURRENCY` sets processes per container).
- Workers scale horizontally; jobs are claimed with `FOR UPDATE SKIP LOCKED` on
  PostgreSQL plus a conditional update, so two workers never take the same job, and a
  meeting never has two drafts running at once. Failed drafts retry three times with
  backoff. Stuck jobs are re-queued after 15 minutes.
- Files: use S3-compatible storage (`S3_BUCKET`) whenever web and worker containers
  do not share a disk.
- Polling keeps the infrastructure simple. If a deployment grows to thousands of
  simultaneous live meetings, swap `/live` polling for WebSockets backed by Postgres
  LISTEN/NOTIFY or Redis.
