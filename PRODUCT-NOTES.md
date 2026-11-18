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

These are demonstrative in-memory behaviors. They do not implement distributed locking, real provider idempotency, durable recovery or access control. A real calendar would need to provide a stable request reference and authoritative booking lookup; the simulation supplies deterministic outcomes only.

## Boundaries

- No diagnosis, prescribing, treatment eligibility, individualized price guarantees or payment collection.
- No live phone calls, SMS, audio, real transfers, external clinic data or background retries.
- No real-time calendar integration or multi-user collaboration. The named staff member is a fictional demo identity.
- No permanent patient records. Do not use real data; the sample details are supplied for trying the flow.
- No clinical emergency advice is generated. The sample clinical question is routed to clinic staff.
- No measured conversion improvement is claimed. The reported association between fast callbacks and bookings would require a fair experiment before making causal claims.

The prior planning handoff contains a broader risk register. This prototype covers representative behaviors within a two-screen case exercise; it does not claim to implement every production edge case.
