# Product scope and behavior

## The two screens

The first screen explains the AI callback, captures the minimum useful routing information and confirms the contact preference. Submission changes the same screen to an inline request/booking state.

The second screen gives clinic staff an enquiry queue and a detail panel. It makes the difference between a confirmed appointment, an uncertain request and an unfinished human handoff visible. Detail panels, inline scheduling and confirmation states are part of these two screens.

The prototype starts with six fictional enquiries across three fictional pilot locations. Its counters describe only this small demo session, not HappySmile's actual business performance.

## Implemented edge-case behavior

| Situation | Prototype behavior |
| --- | --- |
| Invalid name, number or contact preference | Actionable errors; no enquiry is created. |
| Rapid repeated submission | The request key returns the same enquiry instead of creating another. |
| Shared household number | Separate patient requests are allowed; phone equality does not silently merge identities. |
| Scheduled callback | Past, closed-hour, invalid and overly distant dates are rejected. A future callback cannot run early. |
| No appointment yet | A connected call or a selected preference is not displayed as a confirmed booking. |
| Callback requested for later | One scheduled outcome is recorded without creating an appointment. |
| Transfer unanswered | A visible, unassigned follow-up remains in the staff queue with an explicit reason and due time. |
| Language outside supported set | Staff follow-up replaces guessing or automatic booking. |
| Calendar response uncertain | No appointment is promised; staff must check the existing request rather than create a second one. |
| Two requests for the same slot | The in-memory calendar gives the next available slot in that clinic. A full calendar routes to staff. |
| Staff takes over during simulation | The operation version changes; late AI timers cannot complete a contradictory booking. |
| Patient stops contact | Pending callback work is invalidated and the enquiry cannot restart automatically. |
| Contact stopped after booking | The appointment stays confirmed; contact and appointment status remain separate. |
| Callback preference changed | The earlier operation is invalidated and a new preference is recorded with its actor. |
| Repeated staff claim/reconciliation | Invalid repeated actions return an error instead of silently applying another mutation. |
| Filters find no records | A useful empty state appears, without invented records. |
| Reset while callback is running | Timers are cancelled and callbacks cannot reappear in the clean session. |
| Browser refresh | The fictional session resets; the page states this explicitly. |
| Entered text | All user-derived content is escaped before insertion into rendered HTML. |

The table above describes the sample in-memory demonstration. The separate live backend now adds persistent dispatch records, admission transactions, access control and restart recovery. A real calendar would still need an authoritative booking lookup; the live backend only collects requests for staff review.

## Boundaries

- No diagnosis, prescribing, treatment eligibility, individualized price guarantees or payment collection.
- The sample mode makes no calls. The optional backend implements live test calls and optional staff transfers; SMS, real clinic data and automatic retries remain absent.
- No real-time calendar integration or multi-user collaboration. The named staff member is a fictional demo identity.
- Sample records reset in memory. Live test records persist in local SQLite as structured outcomes, masked identifiers and staff tasks. Use only your own consented test phone and fictional preferences during acceptance testing.
- No clinical emergency advice is generated. The sample clinical question is routed to clinic staff.
- No measured conversion improvement is claimed. The reported association between fast callbacks and bookings would require a fair experiment before making causal claims.

The prior planning handoff contains a broader risk register. This prototype covers representative behaviors within a two-screen case exercise; it does not claim to implement every production edge case.

## Live voice extension

The patient screen now has an operator connection/preparation/call control, and the clinic screen displays durable real-call records separately from the sample queue. The application still has two screens. Live speech uses Pipecat Flows, local Whisper, Ollama and Kokoro; Twilio supplies the first phone transport.

The backend validates fixed-destination call admission, limits concurrency and calling hours, records uncertain launches without redialling, verifies signed carrier events and media capabilities, and blocks stale model actions after hangup/stop. Only approved script lines reach TTS. Confirmations require an explicit fresh yes after a completed read-back, with revision checks and interruption invalidation. Staff transfer acceptance and appointment confirmation are not inferred.

No end-to-end phone/audio validation has been performed here. See `VOICE-SETUP.md` and `REAL-CALL-CHECKLIST.md` for configuration and the complete coverage matrix. The current scope is supervised English calls to the operator's own configured phone; real calendar booking, callback scheduling, multilingual support, production staff identity/roles, notifications and retention tooling remain outside it.
