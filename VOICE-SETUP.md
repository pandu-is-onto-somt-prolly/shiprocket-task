# Set up actual phone calls

Vercel serves the interface; your own machine/server runs the speech models and voice backend. The first telephony adapter is Twilio. Other carriers are not implemented in this release.

The software avoids Bolna and hosted inference fees. Telephone networks, compute, electricity, hosting and carrier features can still cost money. Check the carrier's current country availability, verified destinations and outbound permissions before provisioning a number. Trial accounts can restrict destinations or play an announcement; no trial credit amount is assumed.

## 1. Deploy the interface

Upload the complete extracted source to GitHub and import it into Vercel with the included configuration. Copy the frontend's exact HTTPS origin, for example `https://your-happysmile.vercel.app`. No path or trailing slash belongs in the allowlist. Preview deployments with different origins need their own entries.

Only the frontend is deployed by this configuration. The Python backend runs separately to keep inference on hardware you control. Do not put carrier secrets in frontend source or public environment variables.

## 2. Prepare the host and secrets

Install Docker with Compose on a machine that stays awake during calls. On Windows this commonly means Docker Desktop with a working Linux/WSL2 engine. Model downloads need internet access and several gigabytes of disk space. The default seven-billion-parameter Ollama model is sensitive to available RAM/CPU. A slow laptop can hit the response watchdog. Hardware capacity and latency have not been benchmarked for this package.

In the project directory, copy the environment template:

```powershell
Copy-Item .env.example .env
```

Generate a random operator token locally, for example:

```sh
python -c "import secrets; print(secrets.token_urlsafe(40))"
```

Put it in `VOICE_API_TOKEN`. Configure carrier secrets locally; do not paste them into chat, screenshots or GitHub. Keep the token stable with the database: it also keys destination suppression hashes and media capabilities. Rotating it requires migrating/reviewing suppression records; blindly changing it can break matching.

| Variable | Meaning |
| --- | --- |
| `VOICE_API_TOKEN` | Private random value of at least 32 characters, entered by the operator to connect the page. |
| `VOICE_PUBLIC_URL` | Public HTTPS origin reaching this backend on port 7860, with WebSocket support. |
| `VOICE_ALLOWED_ORIGINS` | Comma-separated exact frontend origins; localhost only for development. |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Your carrier account credentials. |
| `TWILIO_FROM_NUMBER` | Your outbound voice-capable carrier number in E.164 format. |
| `DEMO_TO_NUMBER` | Your own verified, consented phone in E.164 format. The page cannot override it. |
| `LIVE_CALLS_ENABLED` | Keep `false` during setup; set `true` when ready for test calls. |
| `STAFF_PHONE_NUMBER` | Optional consenting staff destination; empty means task only. Must differ from the caller/test numbers. |
| `TWILIO_AMD_ENABLED` | Default `true`; asynchronous machine/fax detection. Carrier charges/accuracy may apply. |
| `OLLAMA_MODEL` | Default `qwen2.5:7b`; replacements must support tool calls and pass readiness. |
| `WHISPER_MODEL` | Default `base`, using local CPU/int8 transcription. |
| `MAX_CALL_SECONDS` | Default 180; allowed 30-300. Set on the carrier and locally. |
| `MAX_DAILY_CALLS` | Default 10; allowed 1-30, counted by real India calendar day. |

Admission also requires explicit owner permission, 9 AM-8 PM India time, no active/uncertain call and a three-minute cooldown. The fictional demo clock does not control real calls.

## 3. Start the backend

```sh
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b
```

Pull the exact replacement if you change `OLLAMA_MODEL`. Ollama is private to the Docker network; no public inference port is exposed. The voice backend binds to localhost port 7860 on the host.

Check `http://127.0.0.1:7860/health`. A `status: ok` response proves HTTP reachability, not model/audio readiness.

Expose port 7860 through a trusted HTTPS reverse proxy or tunnel supporting WebSockets. For example, after installing/authenticating ngrok on your machine:

```sh
ngrok http 7860
```

Set `VOICE_PUBLIC_URL` to its HTTPS origin. Keep the tunnel running. If its origin changes, update the environment. Carrier callbacks cannot use localhost. Do not expose Ollama.

Set the exact frontend origin, carrier values and `LIVE_CALLS_ENABLED=true`, then recreate the backend to apply changed environment values:

```sh
docker compose up -d --force-recreate voice
```

Restart alone does not apply changed environment configuration. The `voice-data` mount preserves SQLite; model volumes preserve downloads. Do not remove these while calls or unresolved tasks exist.

The app supplies per-call media/status/AMD/transfer URLs automatically. This outbound path uses inline TwiML and does not need an inbound-number webhook. Forward `/media/*`, `/webhooks/*` and API routes unchanged. Rewriting callback paths/query strings can break signatures.

## 4. Check before dialling

```sh
docker compose exec voice python -m unittest discover -s voice_backend/tests -v
```

Tests use fake carrier responses and do not dial. HTTP tests should run rather than skip inside the installed container. Resolve image/import/test failures first. Direct dependency versions are pinned in `voice_backend/requirements.txt`; transitive dependencies and base images are not fully locked. The Docker build has not been executed in the authoring environment.

## 5. Make a consented test call

1. Open the Vercel page. Expand **Connect your voice backend**; enter its HTTPS origin and private operator token. Do not give this token to patients or public reviewers.
2. Click **Prepare local voice models**. It checks adapter symbols, loads Whisper/Kokoro assets and requests an Ollama tool-call response. It does not dial. Preparation is not an end-to-end audio test. If first downloads exceed the timeout, let that work finish and inspect the host before trying preparation again.
3. Select clinic/service. The live agent verifies these with you. The form's name/free-text phone are not sent to the live backend. Live tests always use the server-configured number and English.
4. Tick the test-phone permission box and click **Call my test phone** once. Answer your phone. There is no automatic retry.
5. Confirm requesting the test call; give clinic/service and an exact date/time. Let the read-back finish, then say a clear **yes**. Expect **appointment requested** and a staff task, never a confirmed booking.
6. Inspect the real record in the clinic workspace, separately from sample enquiries. Claim staff work before resolving it. The shared operator identity is not production staff authentication.
7. Run `REAL-CALL-CHECKLIST.md`, respecting limits. Prepare a new pipeline for each call.

Optional transfer requires a distinct staff number whose owner agrees to testing. A successful carrier update means **transfer requested**, not **staff connected**. Unanswered/busy/dropped transfers leave follow-up unresolved; staff must verify ownership and completion explicitly.

## Recovery

| Symptom | Action |
| --- | --- |
| Vercel cannot connect | Check backend health, HTTPS tunnel, exact origin and token before calling. |
| Models not ready | Check Docker memory, downloads, disk, model name and imports. Preparation does not dial. |
| Phone does not ring | Inspect the existing record and carrier console: destination verification, voice capability, country permissions and account restrictions. Do not retry a timeout blindly. |
| `dispatch unknown` | The carrier may have accepted the call. Verify there is no active call in its console before clearing it. Otherwise end it there. |
| Active record after crash | Use **Check carrier status** for a known SID. An interrupted create without a SID becomes uncertain after stale recovery. If still `creating`, wait five minutes, restart, then reconcile. |
| Hangup unconfirmed | Hang up your phone, inspect/end it in the carrier console and retry stop/status. Suppression remains active despite network errors. |
| Silence/garbled/slow audio | Check host load, model latency, tunnel and sample-rate conversion with a real phone. Duration/watchdog limits bound the failure, but quality needs live testing. |
| Opt-out prevents more calls | Expected. With fresh owner permission, tick consent and use **Record new test-call permission**. This does not dial. |
| No staff notification | This release shows tasks only in the authenticated workspace. A person must monitor it; no email/SMS/push is sent. |

Closing the browser or resetting the sample demo does not hang up a live call. Use the stop control or hang up the phone. After a lost launch response, reconnect and inspect status; a call may still be dialling. Persistent idempotency prevents the same request creating another call, and admission blocks new keys while a call is active/uncertain. The carrier duration cap is independent of the browser/backend.

Content-bearing Pipecat debug output is suppressed by default. Avoid enabling transcript/audio logs with sensitive data. Carrier-side logs, tunnel inspection and provider retention are configured separately.

## Deployment limits

This is a supervised, fixed-destination English test, not a patient campaign dialler. It makes no clinical decisions, checks no real availability and schedules no automatic callback. An urgent task is not an emergency response service.

Use one backend process/worker on one host with persistent SQLite. Horizontal scaling, per-staff roles/audit, tenant isolation, queue notifications, retention/deletion tooling, real calendar reconciliation, alternative carrier adapters and operational monitoring remain future work. Policy tests cannot prove speech understanding, voicemail detection or every real-world edge case.

Maintainer references: [Pipecat](https://github.com/pipecat-ai/pipecat), [Twilio Calls](https://www.twilio.com/docs/voice/api/call-resource), [Twilio security](https://www.twilio.com/docs/usage/security), [Ollama](https://github.com/ollama/ollama), [Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx). Review dependency and model/voice licenses before distribution.
