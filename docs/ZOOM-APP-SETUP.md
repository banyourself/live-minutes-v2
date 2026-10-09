# The Live Minutes app for Zoom

I run one Zoom app for every Live Minutes user. Anyone with a personal workspace or an organization can connect the
Zoom account that hosts their meetings, then import its cloud recordings' transcripts and chat. The app only reads:
it cannot join, record, or change anything in Zoom. The public help page is
https://minutes.kevinle.tech/help/zoom.

## 1. Create the app (once, in my own Zoom account)

1. Sign in at https://marketplace.zoom.us with my own Zoom account. Choose Develop, Build App, **General App**, Create.
2. **Basic Information**: name the app "Live Minutes" and choose **User-managed** under "Select how the app is managed".
3. **OAuth Information**, in both the Development and Production views (each has its own Client ID and Client Secret):
   - OAuth Redirect URL: `https://minutes.kevinle.tech/api/zoom/callback`
   - OAuth Allow List: `https://minutes.kevinle.tech`
4. **Scopes**: add exactly these four, each with its description. Nothing else.

   | Scope | Description to enter |
   |---|---|
   | `user:read:user` | Shows which Zoom account is connected, and recognizes it when the user removes the app so its saved sign-in is deleted. |
   | `user:read:settings` | Checks that cloud recording, audio transcripts, and saved chat are turned on, and shows the user a setup checklist. |
   | `cloud_recording:read:list_user_recordings` | Lists the user's cloud recordings so they can choose which meeting to import. |
   | `cloud_recording:read:list_recording_files` | Reads the closed captions, transcript, chat, and media files of the recording the user chooses, to draft minutes. |

5. **Features, Access**: copy the **Secret Token**. It signs the events Zoom sends.
6. Put the credentials on the server myself. On the VM, edit `/opt/live-minutes/app/.env`:

   ```
   ZOOM_APP_CLIENT_ID=...
   ZOOM_APP_CLIENT_SECRET=...
   ZOOM_APP_SECRET_TOKEN=...
   ```

   Then recreate the containers from `/opt/live-minutes/app` with `docker compose --profile tunnel up -d`, so the new
   values are read. Use the Development credentials while testing and switch to the Production ones before publishing.
   `deploy/oracle/update.sh` keeps this file between deploys.
7. For automatic imports, turn on **Event Subscription** with the endpoint `https://minutes.kevinle.tech/api/zoom/events`
   and add only **Recording, All Recordings have completed** (`recording.completed`) and **Recording, Recording transcript
   files have completed** (`recording.transcript_completed`). Check Scopes afterward: if the picker added a scope, remove the
   events again unless that scope is acceptable to the review. Without these events, everything else still works, and
   imports stay manual. The event sent when a user
   removes the app (`app_deauthorized`) is not in the event picker. Zoom sends it only for published apps, to the
   Deauthorization Notification Endpoint URL set in the listing (see section 3).
8. Test it: choose **Local Test**, then **Add App Now**, or open Live Minutes, Settings, Zoom, and choose Connect Zoom.
   Only accounts in my own Zoom account can add the app until it is published. While testing, use Disconnect Zoom in
   Live Minutes rather than removing the app in Zoom, since a development app sends no removal event.

## 2. How connecting works

- **From Live Minutes**: Settings, Zoom, Connect Zoom sends the person to Zoom with a random `state` kept in a
  10-minute encrypted cookie. The callback checks the state, the person, and their role, then saves the connection.
- **From the Zoom App Marketplace**: Zoom sends the person to the callback without a state. Live Minutes exchanges the
  code, keeps the tokens encrypted in a waiting row for 15 minutes, and asks the signed-in person to choose a
  workspace where they run meetings. Cancelling revokes the tokens. Waiting rows that expire are revoked and deleted.
- **Removing the app**: Disconnect Zoom in Settings revokes the token at Zoom and deletes the connection. Removing the
  app in Zoom sends a signed `app_deauthorized` event, and Live Minutes deletes every connection for that Zoom user.
  Imported meetings stay until someone deletes them. Every event's `x-zm-signature` is checked against the Secret
  Token, and events older than five minutes are refused.
- Tokens are refreshed under a row lock, so two requests at once cannot both use the same refresh token.
- **Captions first**: when a recording has Zoom's saved closed captions (file type `CC`, from "Save closed captions as a
  VTT file") that are at least 60 percent as long as its audio transcript, Live Minutes imports the captions instead of
  the transcript. Otherwise it uses the audio transcript, so a meeting where captions started late is not cut short.
  The settings checklist shows whether caption saving is on.

## 3. Publish on the Zoom App Marketplace

Publishing lets anyone add the app, with no 100-user cap. Zoom does not require a penetration test for a published
app, but it does for a beta share link, so I skip the beta link.

- **App listing**: name "Live Minutes", a short description (150 characters or fewer), a long description with a
  feature list, a 160 by 160 icon in light and dark versions (`docs/zoom-listing/icon-light-160.png` and
  `icon-dark-160.png`, drawn from the site's favicon, with 512 by 512 copies), and two or three 1200 by 780 screenshots.
- **Links and support**, all on my own domain:
  - Support: https://minutes.kevinle.tech/support
  - Documentation: https://minutes.kevinle.tech/help/zoom (adding, using, and removing the app, and what happens to
    data after removal)
  - Privacy policy: https://minutes.kevinle.tech/privacy
  - Terms of use: https://minutes.kevinle.tech/terms
  - Company name: Kevin Le, the same name the policies use.
  - Deauthorization Notification Endpoint URL: `https://minutes.kevinle.tech/api/zoom/events`. Zoom signs the
    removal event with the Secret Token, so the Production Secret Token must be on the server first.
- **Domain verification** for `minutes.kevinle.tech`, by HTML file, meta tag, or DNS TXT record.
- **Technical Design**: the stack (FastAPI, PostgreSQL, React, Docker on an Oracle Cloud VM behind a Cloudflare
  Tunnel), an architecture diagram, and the security answers: TLS 1.2 or newer, signed events checked with the
  Secret Token, and Zoom tokens encrypted at rest with Fernet.
- **For reviewers**: a test plan link in the release notes and a reviewer account. I send the reviewer's email a
  personal workspace invitation from the Platform page, Organizations tab.

## School and company Zoom accounts

A school or company's Zoom admin can require approval before anyone on that account adds an outside app, and Zoom
turns that on by default for multi-user accounts. People on those accounts click "Request pre-approval" in the
Marketplace, and their admin approves it under Active requests. Live Minutes cannot skip that step. Personal Zoom
accounts are not affected. The ASG meetings are hosted on the district's account, so connecting them still needs the
district's Zoom admin (see [IT-REVIEW.md](IT-REVIEW.md)).

## RTMS (live transcripts streamed by Zoom)

Intentionally not built yet. Before any code is useful it needs:

1. The Zoom app registered with RTMS transcript scopes.
2. The host's Zoom account enabling RTMS for that app.
3. A public HTTPS endpoint for Zoom's `meeting.rtms_started` webhook.
4. The host account authorizing the app, with RTMS set to start automatically.

Until then, live capture uses the browser extension, which only reads captions
already shown to a participant. When approved, `minutes_app/rtms.py` should feed each
transcript line into the session with `transcript.add(speaker, text, "rtms", t=ts)`
using Zoom's official RTMS SDK (https://developers.zoom.us/docs/rtms/), so it merges
with the other sources.
