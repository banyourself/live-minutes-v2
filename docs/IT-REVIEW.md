# Live Minutes: Review Packet for District IT

Prepared by Kevin Le, ASG Secretary, Coastline College. For discussion with district IT
and the ASG host account. Nothing in "Needs a decision" is active until approved.

## What it is

A tool that drafts meeting minutes in an organization's own Word template from the
meeting's captions, transcript, and chat. **A secretary reviews every draft, and the
body adopts minutes by motion as always.** The tool never publishes anything.

## Editions

| Edition | Where data lives |
|---|---|
| **Self-hosted server** (recommended) | District servers: PostgreSQL plus a file volume or district S3 bucket. |
| Shared hosted server | The operator's cloud account. Requires a data agreement before use. |
| Desktop app | No data of its own; it shows the chosen server and reads Zoom captions. |
| Local single-user app | The secretary's computer only. |

## What works without any approval

| Piece | What it touches |
|---|---|
| Caption reader (desktop app or Chrome extension) | The caption/transcript panel a participant can already see in the Zoom web client. It does not join, record, click, or change anything in Zoom. |
| Manual import | Transcripts or chat files the host chooses to share. |

## Needs a decision

1. **Hosting:** self-host on district infrastructure, or approve a hosted operator.
2. **AI provider:** which providers organizations may connect. Options include a
   campus-hosted or local model so meeting text never leaves the district.
3. **Zoom app (optional):** the Live Minutes Zoom app, which the host account authorizes once, with
   read-only access to that account's cloud recording transcripts and chat files.
   Scopes: list recordings and read recording files. No scopes to join, record, edit,
   delete, or read other users' meetings. Revocable from the app or from Zoom.
4. **School sign-in:** register the app with Google Workspace or Microsoft Entra ID.

## Data handling

| Data | Stored | Protection |
|---|---|---|
| Accounts | email, name, password hash (scrypt) or SSO identity | sessions are hashed tokens in HttpOnly cookies |
| Meeting text | caption lines, imported transcripts, chat | access limited to members of the owning organization |
| Templates and Word exports | file storage | per-organization paths |
| AI keys, Zoom tokens | database | encrypted at rest |
| Activity log | who did what and when | visible to organization owners |

- **Sent to third parties:** only the meeting text needed to draft, sent to the AI
  provider the organization chose, under that provider's API terms.
- **Not collected:** passwords to Zoom or other services. Audio and video are stored only when
  someone uploads a recording or chooses to import a Zoom recording's media.
- **Deletion:** owners can delete a meeting, which removes its transcript, drafts, and
  files. Removing a member revokes their access and capture tokens.
- **Accessibility:** the web app uses standard HTML form controls and Word exports keep
  the organization's own heading structure, but no formal accessibility audit (VPAT)
  has been done yet.

## Brown Act and transparency

ASG meetings are public, recorded, and transcribed already. The tool adds no hidden
recorder. Recommended: the Chair notes at call to order that the Secretary uses AI
assistance to draft minutes. Uncertain names and facts are marked `[verify]`.

## Questions for IT

1. Self-host on district infrastructure, or evaluate a hosted operator?
2. Which AI providers are acceptable for public-meeting text?
3. Approve the read-only Zoom app for the ASG host account only?
4. Retention period for working transcripts after minutes are adopted?
