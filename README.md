# HappySmile · Care Connect

A complete, interactive two-screen product prototype: a patient requests an AI callback, and the clinic sees the enquiry, outcome and next action.

**This is a simulation.** It does not dial numbers, send messages, record audio, make real appointments, connect to a CRM, or send enquiry data to a server. Refreshing the page resets the session. Please use the sample details.

## Fastest route: paste one file into GitHub

1. Open the `index.html` file from this ZIP in a text editor and copy its contents.
2. Create a GitHub repository, choose **Add file → Create new file**, and name the file **`index.html`**.
3. Paste the entire code and commit it. The filename must be lowercase.
4. In Vercel, import that GitHub repository.
5. Choose **Other** as the framework preset. Leave the build command empty. Use **`.`** as the output directory and leave the root directory at the repository root.
6. Deploy. No API keys, dependencies or environment variables are required.

For this one-file route, you need only `index.html`. Do not copy the full-project `vercel.json`, because that configuration points to the `dist` directory.

You can also double-click `index.html` locally to try the one-file demo. Google Fonts is optional: the interface uses system fonts if that request is unavailable.

## Alternative: upload the complete project

Extract the ZIP and upload its **contents** to your GitHub repository, keeping `dist`, `tests`, and the files below in the same relative locations. Do not upload the ZIP itself as your website.

Import that repository into Vercel. The included `vercel.json` supplies these settings:

| Setting | Value |
| --- | --- |
| Framework preset | Other |
| Root directory | Repository root |
| Build command | Empty / no build step |
| Install command | Empty / no installation |
| Output directory | `dist` |
| Environment variables | None |

The complete-project deployment serves the separate files in `dist`. The root `index.html` is a convenience copy for opening locally or using the one-file route.

Official Vercel references: [static build configuration](https://vercel.com/docs/builds/configure-a-build) and [vercel.json settings](https://vercel.com/docs/project-configuration/vercel-json). To share an assignment link, check it in a signed-out browser after deployment; team-level deployment protection may require configuration in your Vercel account.

## Try the demo

### Patient experience

1. Click **Use sample details**.
2. Select a clinic, service and language. Leave **Call me soon** selected, or choose a later callback.
3. Check the callback permission box and submit.
4. For an immediate callback, click **Play simulated callback**. The fictional call progresses for about four seconds.
5. Click **View clinic workspace** to inspect the same enquiry.

### Clinic workspace

- Start in **Needs attention** to see an unanswered transfer, an uncertain booking and an owned follow-up.
- Filter by clinic, search, or switch to all enquiries / confirmed bookings.
- Select an enquiry to see the summary, contact preference, timeline, appointment reference and next task.
- Take ownership, arrange a callback, resolve a follow-up, stop contact, or reconcile the uncertain simulated calendar request.
- A stopped callback does not cancel an already confirmed appointment.

### Scenario controls

Open **Demo controls** at the top of either screen. Choose one of these outcomes **before** playing a new callback:

1. Appointment booked.
2. Patient requests a later callback.
3. Staff transfer is unanswered.
4. Calendar confirmation is uncertain.
5. Requested language is unsupported.

The demo clock is fixed at **10:30 AM IST on the current India calendar date**. Future callbacks are not dialled early. Use **Reset demo** to return to the initial fictional session; reset also cancels in-flight timers.

## Edit the source

| File | Purpose |
| --- | --- |
| `index.html` | Complete, self-contained copy of the prototype; convenient for copy/paste. |
| `dist/index.html` | Page structure for the separate-file version. |
| `dist/style.css` | Responsive visual design, typography and states. |
| `dist/app.js` | Rendering, forms, navigation, filters and simulation timers. |
| `dist/model.mjs` | Enquiry and booking state transitions, validation and sample data. |
| `dist/favicon.svg` | Small inline-authored brand icon. |
| `vercel.json` | Full-project deployment configuration. |
| `bundle.mjs` | Recreates root `index.html` from the separate source files. |
| `preview.mjs` | Optional local static server. |
| `tests/model.test.mjs` | Twenty workflow and edge-case tests using Node's built-in test runner. |
| `PRODUCT-NOTES.md` | Scope, implemented edge cases and prototype limits. |

Edit the separate files in `dist`. To update the self-contained version afterwards, run:

```sh
node bundle.mjs
```

Node.js is needed only for rebuilding the one-file copy, running tests, or using the optional local server. It is not required for visitors or the static Vercel deployment. There are no npm dependencies.

## Optional checks and local server

With a current Node.js installation:

```sh
node --test tests/model.test.mjs
node --check dist/app.js
node preview.mjs
```

The server prints `http://127.0.0.1:4173`. Stop it with Ctrl+C. Opening the separate-file `dist/index.html` directly from disk can fail because browsers restrict module imports on `file://`; use the local server or open the self-contained root `index.html` instead.

## Verification

- All 20 state/workflow tests passed during preparation.
- Source syntax was checked.
- Local browser preview could not connect in the authoring environment. Visual appearance, mobile rendering, keyboard behavior and deployed Vercel behavior have not been browser-verified here.
- Neither GitHub upload nor Vercel deployment has been performed for this package. It is ready for you to upload.

## Before using real patients or real calls

This prototype deliberately has no backend, authentication, durable storage, real scheduling integration, consent-policy enforcement service or telephony provider. Names and records stay in browser memory for the current session; raw phone numbers are validated, masked and not retained in the state model. Do not treat this as production security or healthcare validation.

The booking calendar, clinical handoffs, contact permissions and all operational results are fictional examples. A live system needs clinic-owned rules, reviewed contact/data policies, qualified handling of clinical questions, authoritative booking records, server-side authorization, durable queues and reconciliation, and real integration tests.
