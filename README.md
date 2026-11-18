# HappySmile Care Connect

A two-screen dental callback application with a patient form, clinic workspace, a fictional demonstration, and an optional self-hosted voice backend for real test calls.

The live agent uses **Pipecat Flows + local Whisper + Ollama + Kokoro**. It follows explicit pathways and speaks approved script lines. Twilio connects the actual phone call. No Bolna subscription or cloud speech/model API key is used. Carrier minutes, phone numbers, hosting and optional answering-machine detection can still cost money.

**Start with [VOICE-SETUP.md](VOICE-SETUP.md) for real calls.** Uploading a static page to Vercel alone does not run local speech models or the phone backend. The adapter is implemented but has not been validated on a real phone in the authoring environment. [REAL-CALL-CHECKLIST.md](REAL-CALL-CHECKLIST.md) separates automated coverage from required live acceptance tests.

## Upload to GitHub and Vercel

1. Extract this ZIP. Upload its contents to your GitHub repository, preserving folders. Do not upload the ZIP as your website.
2. Import that repository in Vercel. Use framework **Other**, repository root, and output directory **dist**. The included `vercel.json` provides the settings; there is no frontend build or dependency installation.
3. Deploy the frontend. Follow `VOICE-SETUP.md` to run the Python backend on your own machine or server, then connect it through the page's **Connect your voice backend** section.
4. Keep the filled `.env`, `voice-data` folder, tokens and carrier credentials out of GitHub. Only `.env.example` belongs in the repository.

The root `index.html` is also a self-contained copy you can paste into a new GitHub file. For that route use Vercel output directory `.` and omit the full project's `vercel.json`. It includes the connection controls but still needs the separate voice backend. Opening the file directly is suitable for the simulation; use an HTTPS deployment or local HTTP server for live backend access and origin checks.

## Two modes

| Mode | How to start | What is real |
| --- | --- | --- |
| Sample demonstration | Use sample details, submit, then Play simulated callback | Fictional, in-memory enquiries and calendar outcomes. No phone call. Refresh/reset clears these records. |
| Live phone test | Connect backend, prepare models, check test-phone consent, choose Call my test phone | One outbound call to the server-configured phone. Structured outcomes, suppression and staff tasks persist in SQLite. |

Live records appear separately in the clinic workspace. Sample counters and simulation scenarios do not represent live results. The live agent is **English-only**, even though the sample form demonstrates other languages. It records appointment or callback **requests for staff review**; there is no calendar integration or automatic callback scheduler.

Closing the browser or resetting the sample demonstration does **not** hang up a real call. Use **Stop contact and end call**, or hang up the phone. If termination is uncertain, inspect the carrier console. Never start a second call merely because a browser response timed out.

## Call pathways and safeguards

- Recipient permission -> clinic/service -> exact preference -> spoken read-back -> fresh explicit confirmation -> durable staff task.
- Corrections invalidate the earlier preference and confirmation. Interrupted or early confirmations are rejected by the speech guard.
- Opt-out and wrong-person responses stop outreach; suppression survives process restarts. New owner permission must be recorded explicitly before another test call.
- Human requests, unsupported language, urgent concerns, voicemail, repeated misunderstanding and service failures leave staff work. Optional staff transfer is a request to the carrier, never proof of accepted handoff.
- One live call at a time, fixed destination, daily cap, cooldown, real India calling hours, bounded silence/repair attempts and a carrier duration limit.
- Durable idempotency, uncertain-launch reconciliation, signed carrier webhooks, ordered status processing and expiring single-use media access.

These are implemented safeguards, not a guarantee that speech recognition or real-world calls will handle every situation correctly. The test release is for your own verified phone, not unattended patient campaigns. Staff monitoring is required for the follow-up queue.

## Source map

| File/folder | Purpose |
| --- | --- |
| `dist/index.html`, `dist/style.css` | Page structure and responsive design. |
| `dist/app.js`, `dist/model.mjs` | Sample workflow and fictional calendar. |
| `dist/live.js` | Live controls and structured records. Operator token stays in page memory. |
| `voice_backend/core.py`, `guard.py` | Durable state transitions, admission rules and confirmation guard. |
| `voice_backend/runtime.py` | Pipecat speech pipeline, approved script and pathway tools. |
| `voice_backend/app.py`, `carrier.py` | Authenticated API, signed webhooks, media transport and Twilio calls. |
| `compose.yaml`, `.env.example` | Local inference/backend setup and configuration template. |
| `VOICE-SETUP.md` | Setup, configuration, troubleshooting and operations. |
| `REAL-CALL-CHECKLIST.md` | Behavior matrix and required real-phone tests. |
| `tests`, `voice_backend/tests` | Frontend policy and backend policy/HTTP checks. |
| `bundle.mjs`, `index.html` | Rebuild script and generated one-file frontend. |

Edit the separate files in `dist`, then run `node bundle.mjs` to refresh the self-contained page.

## Verification

```sh
node --test tests/model.test.mjs
node --check dist/app.js
node --check dist/live.js
python -m unittest discover -s voice_backend/tests -v
python -m compileall -q voice_backend
```

With the backend installed, run its HTTP tests inside the container:

```sh
docker compose exec voice python -m unittest discover -s voice_backend/tests -v
```

At packaging, **20 frontend tests and 54 backend policy/transport/guard tests passed**. Eight HTTP tests were skipped because FastAPI/httpx could not be installed in the authoring environment. Python compilation and JavaScript syntax/bundle checks passed. Docker image installation, Pipecat service imports, actual audio, carrier calls and visual browser interaction remain unverified here. Run the checklist on the target machine before using the live feature.

The optional static development server is `node preview.mjs`; use the exact localhost origin it prints in the backend origin allowlist. The frontend has no npm dependencies.

## Data and limits

The sample session is temporary. Live SQLite records retain masked phone digits, an HMAC destination identifier, structured preferences, events, contact suppression and staff task state. They do not contain full phone numbers, raw transcripts or recordings. The configured full test number exists in local environment configuration and is sent to the carrier; carrier-side records are separate. Speech and language models process the call locally after model downloads. Review dependency/provider behavior before any patient deployment.

This release uses one operator token, one process/host, one test destination and SQLite. It has no patient authentication, staff identity/roles, tenant isolation, retention automation, notification delivery, production observability or real booking availability. Task due times are internal targets, not promises that anyone will call. Production use requires those additions and successful live acceptance tests.
