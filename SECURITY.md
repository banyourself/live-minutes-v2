# Security

## Reporting a problem

Email kevin@kevinle.tech with "Live Minutes security" in the subject. Please do not open
a public issue. District IT teams running their own copy should report to their own
security office as well.

## What is exposed to the internet

Only the HTTPS website. Everything behind it needs a signed-in, confirmed account with a
role in the organization, except:

| Path | Why it is public |
|---|---|
| `/api/health`, `/api/ready` | Load balancer checks. They return no data. |
| `/api/auth/signup`, `login`, `logout`, `verify`, `forgot`, `reset` | Signing in. Rate limited and they never reveal whether an account exists. |
| `/api/auth/sso/...` | School sign-in with Google or Microsoft. |
| `/api/providers` | The static list of AI providers shown on the settings page. |
| `/api/capture/...` | Caption capture from the desktop app and extension. Needs a capture token. |
| `/api/assistant/...` | The chat assistant. Members only, rate limited, and counted against the organization's monthly AI limit. The AI sees names and roles but no email addresses. It can only suggest an allowlisted set of changes with no deletions; each one is stored on the server, shown as a summary built by the server, expires in 30 minutes, can be approved once by the person who asked, and runs through the same permission checks as the normal pages. Every suggestion and approval is in the audit log. |
| `/oauth/...`, `/.well-known/...` | OAuth 2.1 for AI apps such as the Claude website and ChatGPT: dynamic client registration limited to https (or localhost) return addresses, a Live Minutes consent page that names where it returns you, PKCE S256 only, single-use authorization codes for 10 minutes (reusing one revokes the grant), one-hour access tokens, rotating refresh tokens for 90 days, all stored only as hashes, and disconnect from My account. |
| `/mcp` | The MCP server for AI apps like Claude Desktop. Needs a personal token (stored only as a hash, 90 days, revocable, optionally read only), rejects requests from other websites' pages, is rate limited, reaches only organizations the person is actually a member of, can save a draft only for a meeting that token just read, and can never approve minutes. |
| `/api/calendar/{link}.ics` | A person's private calendar subscription. The link holds a long random secret that is stored only as a hash; it shows meeting times and Zoom links for that person's organizations, can be replaced or turned off under My account, and wrong links are rate limited. |

A test (`test_every_api_route_requires_sign_in`) fails the build if any other route can be
reached without signing in. API documentation pages are off in production.

The database, file storage, and secret keys should sit on a private network with no
public address. The worker accepts no connections at all.

## Controls

See the security model in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#security-model).
In short: confirmed accounts, shared sign-in limits, `__Host-` session cookies (HttpOnly, never
readable by page scripts or kept in browser storage) with idle timeout, optional two-step sign-in
with an authenticator app and recovery codes, a list of signed-in devices that can each be signed
out, security emails for password and two-step changes, tenant-restricted SSO, CSRF header, strict
CSP and HSTS, host checking, size
limits before parsing, safe Word parsing, encrypted and rotatable stored keys, outbound
AI calls pinned to checked public addresses, and an audit log.

### Links, codes, and tokens

| What | How long it works | Other protection |
|---|---|---|
| Password reset link | 10 minutes, once | A newer link, a password change, or a reset cancels it; using it signs out every other session and revokes AI app, calendar, and capture tokens |
| Two-step sign-in code | One 30-second app code, accepted once, one step either side for clock drift | Asked after a correct password, after school sign-in, and never skipped by a password reset or email link. The in-between sign-in lasts 5 minutes in an encrypted cookie and works once; 5 wrong codes pause it for 15 minutes. Turning it on signs out other devices; turning it off or making new recovery codes needs the password again and a code |
| Recovery codes | 10 codes, each once | Stored only as keyed hashes; using one sends a security email; a platform owner can turn two-step sign-in off for a person who lost their phone, which signs them out everywhere and emails them |
| Email confirmation link | 10 minutes, once | Also needs the password chosen at sign-up (or the same signed-in browser), so nobody can hand you an account they made; a newer link cancels it |
| Reset link made by an administrator | 10 minutes, once | Needs the administrator's password again |
| School email code | 10 minutes | 6 digits, 5 tries, then a new code is needed |
| Password confirmation for risky actions | 10 minutes | Tied to that one session |
| School sign-in, Zoom, and OpenRouter connection steps | 10 minutes | Checked on the server, tied to the person who started them |
| AI app authorization code | 10 minutes, once | PKCE S256; reusing it revokes the app |
| AI app access token | 1 hour | Rotating refresh token for 90 days; reusing an old refresh token disconnects the app |
| Sign-in session | 14 days at most, 12 hours idle | `__Host-` cookie, HttpOnly, SameSite=Lax, Secure |
| Invite link | 7 days by default (1 to 30) | Only works for the invited email address, which still has to be confirmed by email; the link is only shown to the inviter when email is off; only owners and IT can invite someone with permanent full access |
| Capture device token | 180 days by default (7 to 365) | Revocable; stops when its owner loses access or is disabled |

Every link, code, and token is random and stored only as a keyed hash, so a database copy cannot be used to sign in. Changing or resetting a password signs out other sessions and disconnects AI apps, calendar links, and capture devices. An account made only through school sign-in gets a password through an emailed link, not from a signed-in page. When school sign-in reaches an account that was never confirmed by its own email link, the old password and sessions are removed first. With Cloudflare Turnstile on, repeated failed sign-ins slow down that network instead of locking the account for everyone. Each Turnstile token must come from minutes.kevinle.tech and from the form it is used on (sign-up, sign-in, or password reset), as Cloudflare recommends, so a token solved elsewhere is refused.

Passwords are checked against Have I Been Pwned with its k-anonymity range API: only the first five characters of the password's SHA-1 hash leave the server, as that API requires. SHA-1 is used only for that lookup; stored passwords use scrypt.

The AI model never gets tools and its output is never executed. It is checked against
the organization's template and shown to a secretary, who approves the minutes.

AI keys belong to a district, college, organization, or person. Only the owner can see the masked
key, change it, or share it, and sharing only goes downward: a district to its colleges, a college to
its organizations or people. An organization can only use a personal key when its district and college
allow it. Meeting text is sent only to the AI the organization or its secretary picked for that task,
every call is metered, and calls stop once an organization's monthly limit is reached. Prompts tell
the AI to treat transcript text as data, not instructions.

## Roles

| Role | Can see and manage | Granted by |
|---|---|---|
| Platform owner | Everything: all districts, colleges, organizations, accounts, settings, email, and billing | Another platform owner, or `python -m server.manage make-admin` |
| District IT | One district: its colleges and their email domains, organizations, people, join and college requests, and college IT | The platform owner |
| College IT | One college: its organizations, people, and join requests | District IT for that district, or the platform owner |
| Organization owner | One organization's settings, members, and meetings | Whoever creates it, or another owner |

- Every account is a Student, Faculty, Staff, or IT account. Students confirm a student email at their
  college; Faculty, Staff, and IT confirm a work email on the college's staff domains. Only Staff and IT
  accounts can hold IT roles, and switching an account away from Staff or IT removes its IT roles.
- Districts, colleges, and organizations are official: they exist only after the platform owner adds them
  or approves a request. New organizations are approved by that college's IT, the district's IT, or the
  platform owner; new colleges by district IT or the platform owner; new districts only by the platform
  owner. Look-alike names (such as "CCCD" for "Coast Community College District") are flagged before
  approval, and duplicate districts can be merged.
- District and college IT roles require a confirmed **staff** email on that district's or college's
  staff domains. Student domains never qualify.
- Roles are only granted downward and inside the granter's own area. Nobody can grant a role to
  themselves, and college IT cannot grant roles at all.
- IT roles act as an owner for organizations in their area, but cannot disable or delete accounts,
  change server settings, see other areas, or see billing. Those stay with the platform owner.
- Every grant and removal needs the person's password again and is written to the activity log.
- Tests in `RoleHierarchyTests` try each escalation path and fail the build if one works.

### Officer positions

- Positions belong to one organization and add access only while a term is active. When a term ends, the
  access ends at once, even before the worker records it, and the person can be removed from the organization.
- A position can only be assigned by someone whose own position outranks it and has the assign permission, and
  ended by someone who outranks it and has the remove permission. Anyone can step down from their own term.
- Only advisors (Faculty or Staff accounts with a confirmed work email at the college), college IT, district IT,
  and the platform owner can change positions. They can only change positions ranked below their own, set ranks
  below their own, and give permissions and access they have themselves.
- Organization owners can manage positions below Advisor unless an advisor turns that off, and can name the
  first advisor only when the organization has none.
- When an organization has a reviewer, minutes cannot be approved until a reviewer marks them reviewed, and
  editing reviewed minutes sends them back for review. Every change is in the activity log.
- Tests in `OfficerTests` cover each of these rules.

Recordings: uploads are checked by their first bytes and only MP4, M4A, MOV, WebM, MP3, WAV, and OGG are kept, served with
`nosniff` and their real type, and streamed in byte ranges. Uploads arrive in 32 MB parts so they fit under proxy limits;
unfinished uploads are deleted after a day. A legal hold blocks deleting a recording.

Backups: destination keys and SAS tokens are encrypted like AI keys and never shown again; Live Minutes only
writes, so give it a write-only key. Endpoints must be https on a public address, and Azure containers must be
on blob.core.windows.net. Connecting, changing, and running backups need IT's password again and are logged.

Records management: retention, legal holds, and exports are district IT and platform owner actions that
need the password again and are logged. College IT can see holds and export their own college. Exports
leave out AI keys, capture tokens, Zoom tokens, and any setting whose name looks like a secret, are
downloadable only after re-entering the password, and are deleted after 7 days.

School sign-in: Microsoft accepts only tenant IDs set by the server or entered by that district's IT, and a
tenant or Google Workspace domain can belong to only one district. Automatic setup confirms a school email
only when the address is on one of the district's college domains and no other account has confirmed it.
Microsoft sign-in uses the account's sign-in name (which Microsoft only allows on domains the tenant has proven
it owns), or the email address only when Microsoft marks it verified. A school sign-in never attaches itself to
an existing Live Minutes account unless the address is verified or the person is already signed in to that
account, and it never grants platform owner access from an unverified address. That stops a directory admin
from signing in as someone else by typing their address into a directory profile.
Changing these settings needs district IT's password again and is written to the activity log.

Translations send only the text of the minutes as numbered pieces; template headings, names in roll calls, and
file structure never leave the server, and a reply that does not match those pieces exactly is rejected.
Word files are read with `defusedxml`, so a crafted template cannot use XML entity tricks.

CSV exports (voting records and funding requests) prefix any cell that starts with `=`, `+`, `-`, `@`, or a
tab so spreadsheet programs cannot run it as a formula. AI answers to questions only see the numbered
excerpts found for that question, are rate limited per person, and count toward the organization's AI limit.

Meeting links must be `https` Zoom addresses (`zoom.us` or `zoomgov.com` and their subdomains), so a
scheduled meeting cannot point people at another site.

## Administration

Platform owners get the Platform dashboard: people, organizations, join and school
requests, the email outbox (subjects only, never bodies, since those hold sign-in links and
codes), failed sign-ins, settings, and a server-wide activity log. Risky actions (disabling,
deleting, granting admin, one-time reset links, changing settings) ask for the admin's
password again and stay unlocked for 10 minutes. Every setting has safe limits, so the
dashboard cannot, for example, lower the minimum password length below 12. The server
always keeps at least one administrator, and an admin cannot disable or delete their own
account from the dashboard. Maintenance mode signs everyone out except administrators.

## Supply chain

- Python packages are pinned to exact versions with checksums (`server/requirements.txt`,
  built from `server/requirements.in`), and the Docker image installs with
  `--require-hashes`. Base images are pinned by digest, and each build applies the latest
  Debian security updates so fixes land before the upstream image is rebuilt.
- GitHub Actions are pinned to commit SHAs. Dependabot proposes weekly updates.
- Every push runs pip-audit, npm audit, Bandit, Semgrep, a Gitleaks scan of the full
  history, and a Grype scan of the built image. Any high-severity finding fails the build.

## Desktop app

Sandboxed renderer windows with context isolation and no Node access, permission requests
denied except clipboard writes for the configured server, IPC accepted only from the app's
own pages, navigation limited to the server and sign-in pages, a single instance, and
Electron fuses that block running it as plain Node or loading code outside the app
archive. The capture token is encrypted with the operating system's key store.

## Latest assessment

See [docs/SECURITY-ASSESSMENT.md](docs/SECURITY-ASSESSMENT.md) for the most recent test of the live site.

## AI safety (OWASP Top 10 for LLM applications, 2025)

| Risk | What Live Minutes does |
|---|---|
| LLM01 Prompt injection | Transcripts, chat, examples, search excerpts, notes, drafts, and chat messages are wrapped in labeled data tags, and any tag-like text inside them is neutralized. Invisible and bidirectional Unicode characters (zero-width, direction overrides, tag characters) are stripped from everything sent to an AI. Every prompt says data is never instructions. The chat assistant refuses override attempts before calling the AI. |
| LLM02 Sensitive information disclosure | The assistant sees names, roles, and positions only, never email addresses. MCP and the assistant reach only organizations the person belongs to. No keys or secrets are ever placed in a prompt. |
| LLM03 Supply chain | AI providers are an allowlist, custom servers pass the outbound URL guard, and server dependencies are hash-pinned and audited in CI. |
| LLM04 Data and model poisoning | Only secretaries can upload templates and examples; examples are used for style only and wrapped as data. |
| LLM05 Improper output handling | AI output is plain text in the page (React escapes it), page links are allowlisted, suggested changes are allowlisted types validated by the server, drafts are checked against the template, and Word files escape all text. Output has control and invisible characters removed and runaway repetition cut. |
| LLM06 Excessive agency | The assistant and AI apps can only suggest changes; a person presses Approve, the change runs with that person's permissions, nothing is ever deleted, and AI apps cannot approve minutes. |
| LLM07 System prompt leakage | Prompts hold no secrets, every prompt tells the AI not to reveal it, and assistant replies that echo the instructions are replaced. |
| LLM08 Vector and embedding weaknesses | Search is keyword-based and scoped to the person's organization; there is no shared vector store. |
| LLM09 Misinformation | Drafts mark uncertain items with [verify], answers cite numbered sources, and a person reviews and approves all minutes. |
| LLM10 Unbounded consumption | Every call has a small output cap (600 tokens for the assistant and questions, 700 for summaries, 4,096 for drafts), timeouts, per-person rate limits (30 assistant messages per 10 minutes and 150 per day), monthly organization limits, and no AI loops: the drafter retries at most once. Requests to repeat text forever or to write or run code are refused without calling the AI. |

Token use is kept low: the assistant sends only the facts a question needs (members only when people are mentioned,
officer terms only when officers are, meetings only when meetings are), a short system prompt, and the last eight
messages; questions send at most eight excerpts; and Claude caches the long drafting instructions between calls.

