# Live Minutes: HECVAT Lite answers (draft)

Status: draft prepared by the vendor for district review. It describes the software as built and the
current pilot at https://minutes.kevinle.tech. Answers marked "Pilot" change when the district runs its
own deployment. Copy these answers into the current EDUCAUSE HECVAT Lite spreadsheet; question wording
below is summarized, not quoted.

Vendor contact: Kevin Le, kevin@kevinle.tech. Security reports: kevin@kevinle.tech.

## Company and product

| Topic | Answer |
|---|---|
| Product | Live Minutes, a web app that drafts meeting minutes for student governments, clubs, and committees from captions, Zoom transcripts, and chat. A person reviews and approves every draft. |
| Company | Independent project by Kevin Le (student developer). No outside investors. |
| Hosting model | Pilot: one Docker Compose deployment on the vendor's computer, reached only through a Cloudflare Tunnel (no open inbound ports). District: the same container image in the district's own cloud subscription (Azure planned) or on district servers. |
| Data location | Pilot: United States (California). District deployment: wherever the district runs it. |
| Users | Students, faculty, staff, and district IT at the participating colleges. |

## Data

| Topic | Answer |
|---|---|
| Data collected | Meeting recordings that organizations upload or import from Zoom, account name and email, account type (student, faculty, staff, IT), confirmed school email, organization memberships and officer positions, meeting transcripts and chat imported by the secretary, draft and approved minutes, motions and votes, funding requests, and an activity log. No grades, financial aid, health, or ID numbers are collected. |
| FERPA | Minutes of public student-government meetings are generally public records, but transcripts and account data can be education records. Live Minutes acts as a school official under the district's direct control; see the FERPA data protection agreement draft. |
| Sale or advertising | Data is never sold or used for advertising or profiling. |
| AI processing | Meeting text is sent only to the AI provider the district, college, organization, or person chose for that task, with the briefing that text in the record is data and not instructions. Districts and colleges can turn off personal AI keys so text goes only to AIs they approved. Provider choice decides whether the provider retains prompts; districts should pick providers with no-training and zero or short retention terms. |
| Data ownership | The district owns its data. A district or college export gives everything back as one ZIP. |
| Policies | Privacy policy, Terms of use (including recording consent and the college code of conduct), and an accessibility statement are published in the app. Every account accepts the current terms, with the version and time recorded. Only strictly necessary cookies are used, so no cookie banner is needed. |
| Retention and deletion | District IT sets retention rules for never-approved meetings, transcripts of approved minutes, and approved minutes. Legal holds stop all deletion. Deleting an organization or meeting removes its stored files. |
| Backups | Pilot: a nightly PostgreSQL dump and file-storage archive kept 14 days in a backup folder on the host, which should be synced off the machine. District and college IT can also connect their own S3-compatible or Azure Blob storage, choose which kinds of data are copied, and set daily or weekly copies. District deployment: managed database backups. |

## Application security

| Topic | Answer |
|---|---|
| Authentication | Email and password with strict rules (12+ characters, breached-password check through Have I Been Pwned k-anonymity), or school sign-in with Microsoft Entra ID or Google. Districts can register their own Entra tenants and Workspace domains. |
| Multi-factor | Available through school sign-in (the district's own MFA applies), and built-in two-step sign-in for password accounts with an authenticator app (TOTP) and single-use recovery codes. It is asked after school sign-in too when turned on, and a password reset never skips it. It cannot yet be required for everyone by policy. |
| Brute force | Per-account and per-network limits stored in the database, progressive lockout, owner email on repeated failures, optional Cloudflare Turnstile. |
| Sessions | Random tokens stored hashed, `__Host-` cookies (HttpOnly, Secure, SameSite=Lax), 12-hour idle and 14-day absolute limits, sign-out everywhere on password change. Risky admin actions need the password again. |
| Authorization | Role hierarchy: platform owner, district IT, college IT, organization roles, and officer positions with ranked permissions. Every route checks the caller's role; an automated test fails the build if any API route answers without sign-in. |
| Encryption in transit | HTTPS only with HSTS. Pilot: TLS terminates at Cloudflare and travels through the encrypted tunnel. |
| Encryption at rest | AI keys and Zoom tokens are encrypted with rotatable keys. Tokens for capture devices, invites, email links, and calendar links are stored only as hashes. Database and file encryption at rest: pilot depends on the host disk; cloud deployments use the provider's storage encryption. |
| Web protections | Strict Content-Security-Policy with no inline scripts, CSRF header on every change, host checking, request size limits, frame denial, no API docs in production. |
| Outbound calls | AI connections may reach only public addresses, are pinned to the checked address, and never follow redirects. |
| File handling | Word files are checked for zip bombs and parsed with defusedxml. CSV exports neutralize spreadsheet formulas. |
| Logging | Activity log of sign-ins, failures, role and membership changes, AI and Zoom connections, imports, edits, reviews, approvals, exports, holds, retention runs, and deletions. Organization owners, college IT, district IT, and the platform owner each see their own area. |

## Development and operations

| Topic | Answer |
|---|---|
| Source control | Private GitHub repository. Every change runs tests on SQLite and PostgreSQL. |
| Dependencies | Python packages pinned by hash, container images pinned by digest, GitHub Actions pinned by commit. Dependabot with a cooldown. |
| Scanning | Every push runs pip-audit, npm audit, Bandit, Semgrep, Gitleaks, and Grype; high findings fail the build. |
| Testing | 117 server tests and 16 engine tests, including role escalation, tenant isolation, CSRF, key encryption, and SSRF tests. |
| Third-party assessment | Not yet. A self-assessment of the live pilot is in docs/SECURITY-ASSESSMENT.md. An outside test is planned before district rollout. |
| Incident response | Reports to kevin@kevinle.tech. The vendor will notify the district contact without undue delay and within 72 hours of confirming a breach of district data, with what happened, what data, and what was done. |
| Availability | Pilot: best effort on one host, no SLA. District deployment: the district's own cloud or servers, with worker and web replicas. |

## Accessibility

See the accessibility conformance report draft. Word exports carry a title and language and can be
checked for headings, image descriptions, table headers, spacing, text size, contrast, and link text.
