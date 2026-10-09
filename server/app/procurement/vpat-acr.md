# Live Minutes: Accessibility Conformance Report (draft)

Based on the VPAT 2.5 format, WCAG edition. Status: draft prepared by the vendor without a third-party
audit. "Supports" below means the feature was built for the criterion and spot-checked by the vendor;
the district should confirm with its own testing or an outside audit before relying on this report.

- Product: Live Minutes web app (current release at https://minutes.kevinle.tech)
- Report date: October 2026
- Contact: Kevin Le, kevin@kevinle.tech
- Evaluation methods: manual keyboard checks, screen reader spot checks, code review of markup, and the
  built-in Word accessibility checker for exported minutes.
- Applicable standard: WCAG 2.1 Level A and AA.

Conformance levels: Supports, Partially Supports, Does Not Support, Not Applicable, Not Evaluated.

## WCAG 2.1 Level A

| Criterion | Level | Remarks |
|---|---|---|
| 1.1.1 Non-text Content | Partially Supports | The logo has empty alt text as decoration. Icon-only controls are few; each button has visible text. Images inside uploaded templates depend on the template; the Word checker flags missing descriptions. |
| 1.2.1 to 1.2.3 Audio and Video | Not Applicable | The app does not publish audio or video. |
| 1.3.1 Info and Relationships | Partially Supports | Forms use labels wrapping their inputs, tables use header cells, and pages use headings. Some status chips convey meaning that is also stated in text. Not yet tested across every screen. |
| 1.3.2 Meaningful Sequence | Supports | Content order in the markup matches the visual order. |
| 1.3.3 Sensory Characteristics | Supports | Instructions do not rely on shape or position alone. |
| 1.4.1 Use of Color | Partially Supports | Status chips use color and words together. Some highlighted rows rely on a border color. |
| 1.4.2 Audio Control | Not Applicable | No audio plays. |
| 2.1.1 Keyboard | Partially Supports | Controls are native buttons, links, inputs, and selects. The month calendar and drag-free layouts work by keyboard; complex editors are not yet fully tested. |
| 2.1.2 No Keyboard Trap | Supports | No custom focus traps except the password confirmation dialog, which closes with its buttons. |
| 2.1.4 Character Key Shortcuts | Not Applicable | No single-key shortcuts. |
| 2.2.1 Timing Adjustable | Supports | Sessions end after 12 idle hours. Ten minutes before, a dialog warns the person and lets them stay signed in. |
| 2.2.2 Pause, Stop, Hide | Supports | There is no auto-playing animation. The device's reduced-motion setting is respected, and Customize can turn animations off. |
| 2.3.1 Three Flashes | Supports | Nothing flashes. |
| 2.4.1 Bypass Blocks | Supports | A skip link is the first focusable element and jumps to the main content. |
| 2.4.2 Page Titled | Supports | Each page sets a descriptive title, such as "Voting record · Live Minutes". |
| 2.4.3 Focus Order | Supports | Focus follows the reading order. |
| 2.4.4 Link Purpose | Supports | Links name their destination, such as the meeting title. |
| 3.1.1 Language of Page | Supports | Pages declare English. Exported Word files declare their language, including translations. |
| 3.2.1 On Focus, 3.2.2 On Input | Supports | Focus does not change context. Settings toggles save immediately and say so. |
| 3.3.1 Error Identification | Supports | Errors appear as text in an alert region describing what to fix. |
| 3.3.2 Labels or Instructions | Supports | Inputs have visible labels; complex inputs include examples. |
| 4.1.1 Parsing | Supports | React renders valid markup. |
| 4.1.2 Name, Role, Value | Supports | Native controls expose name and role. Tab bars and option buttons are grouped and expose their selected state with aria-pressed. Inputs without a visible label have an accessible name. |

## WCAG 2.1 Level AA

| Criterion | Level | Remarks |
|---|---|---|
| 1.2.4, 1.2.5 Captions and Audio Description | Not Applicable | No media. The product itself produces text records of meetings. |
| 1.3.4 Orientation | Supports | Layouts work in both orientations. |
| 1.3.5 Identify Input Purpose | Partially Supports | Sign-in fields use autocomplete for email and password; other personal fields do not yet. |
| 1.4.3 Contrast (Minimum) | Supports | Measured: body, helper, and placeholder text in every built-in color scheme are at least 4.5:1 against cards, fields, and tabs. A custom background color chosen by the user can lower contrast; a high-contrast setting is available under Customize. |
| 1.4.4 Resize Text | Supports | Text resizes to 200 percent without loss of content. |
| 1.4.5 Images of Text | Supports | No images of text. |
| 1.4.10 Reflow | Partially Supports | Most pages reflow at 320 CSS pixels; wide tables scroll sideways. |
| 1.4.11 Non-text Contrast | Not Evaluated | |
| 1.4.12 Text Spacing | Not Evaluated | |
| 1.4.13 Content on Hover or Focus | Supports | No hover-only content. |
| 2.4.5 Multiple Ways | Supports | Navigation menu and search across minutes. |
| 2.4.6 Headings and Labels | Supports | Headings and labels describe their content. |
| 2.4.7 Focus Visible | Supports | Every link, button, and field shows a 3-pixel outline in the accent color when focused by keyboard. |
| 3.1.2 Language of Parts | Partially Supports | Translated minutes are exported in their own file with their own language. Mixed-language text in the web view is not marked. |
| 3.2.3 Consistent Navigation, 3.2.4 Consistent Identification | Supports | The same side menu and labels appear on every page. |
| 3.3.3 Error Suggestion | Supports | Messages say how to fix the problem, such as which email domain to use. |
| 3.3.4 Error Prevention | Supports | Risky actions ask for confirmation or the password again. Minutes need approval, and approved minutes must be reopened before editing. |
| 4.1.3 Status Messages | Supports | Errors use role alert and success notices use role status, so screen readers announce both. |

## Exported documents

Every Word file Live Minutes builds has a title and document language. The Summary and translations tab
checks each file for headings, image descriptions, table header rows, stacks of empty lines, text under
9 point, low-contrast text, and vague link text, and explains how to fix template issues.

## Planned work

Non-text contrast (1.4.11) and text spacing (1.4.12) measurement, autocomplete on remaining personal
fields, reflow of wide tables at 320 pixels, and an outside audit before district rollout. An
accessibility statement with a way to report barriers is published at /accessibility.
