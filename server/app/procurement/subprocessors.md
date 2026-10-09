# Live Minutes: subprocessors and data flow

Status: current for the pilot at https://minutes.kevinle.tech. A district deployment replaces the
hosting rows with the district's own services.

| Service | What it does | District data it handles | Notes |
|---|---|---|---|
| Cloudflare (tunnel, DNS, TLS) | Carries web traffic to the server and terminates HTTPS | All web traffic in transit | No inbound ports are open on the host. |
| Cloudflare R2 (offsite backups, hosted service only) | Stores nightly copies of the server backups | Database and file backups, encrypted before upload | Encrypted with a public key; the private key is kept offline by the operator, so Cloudflare cannot read them. Deleted after 30 days. |
| Cloudflare Turnstile | Bot check on sign-up and sign-in | Browser signals for the check only | Can be turned off. |
| Resend (email) | Sends sign-in links, codes, invites, and notifications | Recipient email and message text | Messages include meeting titles, times, Zoom links, reviewer notes, and weekly summaries, not transcripts or minutes. People choose which notification emails they get. |
| AI provider chosen in the app | Drafts minutes, answers questions, translates, and summarizes | Meeting text for the task | Chosen per district, college, organization, task, or person. Examples: Anthropic, OpenAI, Google, OpenRouter, Groq, xAI, or a campus-hosted model. Districts can require approved providers only. |
| Zoom (optional) | Imports cloud recording transcripts, chat, and, when asked, media | The connected Zoom account's email and IDs, recording settings, recording list, and the files of recordings someone imports | Read only. Off unless an organization or personal workspace connects it; removing the app in Zoom disconnects it. |
| Microsoft Entra ID or Google (optional) | School sign-in | Name, email, and directory IDs | Only for directories the server or district IT allows. |
| Backup storage connected by district or college IT (optional) | Receives scheduled copies of the records they choose | The data kinds selected for that destination | Amazon S3, Cloudflare R2, Backblaze B2, Wasabi, MinIO, or Azure Blob Storage, under the district's own account. |
| Have I Been Pwned | Checks new passwords against known breaches | The first 5 characters of a SHA-1 hash of the password | k-anonymity range lookup. The password itself never leaves the server. |

## Data flow

1. Captions come from the desktop app or Chrome extension with a capture token, or the secretary
   imports a Zoom transcript or chat file.
2. The server stores the transcript in PostgreSQL. The worker sends the transcript and the
   organization's template outline to the chosen AI and stores the draft.
3. The secretary edits and approves the minutes. Word files are built on the server and kept in the
   server's file storage.
4. Exports, translations, and summaries stay on the server unless a person downloads them.
