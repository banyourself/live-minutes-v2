# Microsoft Edge Add-ons listing

What I enter in Partner Center (partner.microsoft.com, Edge program, free) for the Caption Reader. The package is
`Live Minutes Caption Reader <version>.zip`, built from `capture-extension/` and also offered at
https://minutes.kevinle.tech/download.

## Properties

- Category: Productivity
- Privacy policy: https://minutes.kevinle.tech/privacy
- Website: https://minutes.kevinle.tech/download
- Support: https://minutes.kevinle.tech/support
- Mature content: No

## Store listing

**Short description**

Sends the Zoom web client captions you can already see to your Live Minutes meeting, so its minutes draft live.

**Description**

Live Minutes Caption Reader works with Live Minutes (https://minutes.kevinle.tech), which drafts meeting minutes for
student governments, clubs, and committees for a person to review and approve.

When you join a Zoom meeting in the browser with captions turned on, the extension reads the captions shown on the page
and sends each line to the Live Minutes meeting you choose, so the draft minutes update during the meeting.

- Reads only the captions already visible to you in the Zoom web client. It does not record audio or video.
- Sends them only to minutes.kevinle.tech, using a capture token you create in Live Minutes and can revoke.
- Stores only your server address, token, and chosen meeting, in the browser.
- No ads, no analytics, and no data sold or shared.

Tell everyone in the meeting that captions are captured for minutes.

**Search terms:** meeting minutes, Zoom captions, student government, transcript, secretary

## Permission justifications (for reviewers)

- `storage`: keeps the server address, capture token, and chosen meeting.
- Content script on `https://*.zoom.us/*`: reads the caption text in the Zoom web client.
- Optional host `https://minutes.kevinle.tech/*`: requested when the user saves settings, to send captions to Live Minutes.
- `http://localhost/*` and `http://127.0.0.1/*`: sends captions to the Live Minutes desktop app on the same computer
  instead, when the server field is left empty.

## Notes for certification

Testing needs a Live Minutes account and a Zoom meeting joined in the browser. I give the reviewer a test account
with a personal workspace invitation, a capture token, and steps: start a meeting in Live Minutes, choose it in the
extension options, join any Zoom meeting from the browser with captions on, and watch lines arrive on the meeting page.

## Logo

`docs/edge-listing/logo-300.png` (300 by 300), drawn from the same icon as the Zoom listing.

## Screenshots

1280 by 800 or 640 by 400: the options page with a meeting chosen, and a Live Minutes meeting page receiving captions.
