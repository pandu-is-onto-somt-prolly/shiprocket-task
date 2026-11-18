"""Authenticated one-host FastAPI service for a configured test phone."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import re
import time
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .config import Settings
from .core import Store, RuleError, constant_match, media_token, validate_media_token, ACTIVE, TERMINAL
from .carrier import TwilioCarrier, CarrierError, stream_twiml, valid_signature


def create_app(settings=None, carrier=None, warmup_fn=None, run_voice_fn=None):
    settings = settings or Settings.from_env()
    store = Store(settings.database, settings.api_token)
    carrier = carrier or TwilioCarrier(settings)
    sessions, prepared = {}, {"speech": None, "preparing": False, "preparation_task": None}
    preparation_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        # Hard carrier duration is the independent limit if this process is killed.
        for call_id, session in list(sessions.items()):
            try:
                await session["close"]("technical")
            except Exception:
                pass

    app = FastAPI(title="HappySmile self-hosted voice", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.sessions = store, sessions
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"], max_age=600)

    @app.exception_handler(RuleError)
    async def rule_error(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=exc.status, headers={"Cache-Control": "no-store"})

    def authorized(request):
        if not constant_match(request.headers.get("authorization", ""), "Bearer " + settings.api_token):
            raise RuleError("The voice backend access token is missing or incorrect.", 401)
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            raise RuleError("This page origin is not allowed to use the voice backend.", 403)

    async def body(request, *, form=False):
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > 16384:
                raise RuleError("Request body is too large.", 413)
        if form:
            return parse_qsl(data.decode("utf-8"), keep_blank_values=True)
        try:
            value = json.loads(data or b"{}")
        except (ValueError, UnicodeDecodeError):
            raise RuleError("A valid JSON body is required.", 422) from None
        if not isinstance(value, dict):
            raise RuleError("A JSON object is required.", 422)
        return value

    async def signed_form(request):
        if not settings.enabled or not settings.auth_token:
            raise RuleError("Carrier callbacks are disabled.", 403)
        pairs = await body(request, form=True)
        # Canonical public URL is configuration, never a caller-controlled Host header.
        url = settings.public_url + request.url.path
        if request.url.query:
            url += "?" + request.url.query
        if not valid_signature(url, pairs, request.headers.get("x-twilio-signature", ""), settings.auth_token):
            raise RuleError("Invalid carrier webhook signature.", 403)
        return dict(pairs)

    def public_call(record):
        # Do not expose destination hashes or provider credentials to the frontend.
        return {k: record[k] for k in ["id", "last4", "status", "created", "updated", "stage", "outcome", "stopped", "stop_pending", "details", "task", "events"]}

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "self_hosted_voice"}

    @app.get("/api/config")
    async def config(request: Request):
        authorized(request)
        return {"enabled": settings.enabled, "test_last4": settings.test_number[-4:], "language": "English", "max_seconds": settings.max_seconds, "daily_limit": settings.daily_limit, "prepared": prepared["speech"] is not None, "booking_mode": "request_only", "transfer_enabled": bool(settings.staff_number)}

    @app.post("/api/prepare")
    async def prepare(request: Request):
        authorized(request)
        if not settings.enabled:
            raise RuleError("Live calling is disabled in backend configuration.", 503)
        async with preparation_lock:
            if any(r["status"] in ACTIVE for r in store.list()):
                raise RuleError("A call is active or awaiting reconciliation.")
            if prepared["speech"] is None:
                prepared["preparing"] = True
                try:
                    if warmup_fn is None:
                        from .runtime import warmup
                        prepare_fn = warmup
                    else:
                        prepare_fn = warmup_fn
                    if prepared["preparation_task"] is None:
                        prepared["preparation_task"] = asyncio.create_task(prepare_fn(settings))
                    # A timeout must not start a second model download while the
                    # original thread/task is still loading the same files.
                    prepared["speech"] = await asyncio.wait_for(asyncio.shield(prepared["preparation_task"]), timeout=180)
                except TimeoutError:
                    raise RuleError("Model preparation is still running. Wait for the existing download/loading work; preparing again will reuse that attempt. No phone was dialled.", 503) from None
                except Exception:
                    raise RuleError("The local voice models are not ready. Check dependencies, model downloads and Ollama, then try preparation again. No phone was dialled.", 503) from None
                finally:
                    task = prepared["preparation_task"]
                    if task is not None and task.done():
                        prepared["preparing"] = False
                        prepared["preparation_task"] = None
        return {"ready": True}

    @app.post("/api/calls")
    async def calls(request: Request):
        authorized(request)
        if not settings.enabled:
            raise RuleError("Live calling is disabled.", 503)
        data = await body(request)
        if set(data) - {"clinic", "service", "language", "consent"}:
            raise RuleError("Only demo context and consent are accepted. The destination is fixed on the server.", 422)
        key = request.headers.get("idempotency-key", "")
        # Check a retry first so an accepted request can always be recovered, even
        # after the one-use prepared pipeline has been consumed.
        with store.db() as db:
            existing = db.execute("SELECT id FROM calls WHERE request_key=?", (key,)).fetchone()
        if existing:
            return {"call": public_call(store.get(existing[0])), "duplicate": True}
        async with preparation_lock:
            if prepared["speech"] is None:
                raise RuleError("Prepare the local voice models before placing a call.", 503)
            result, duplicate = store.admit(key, settings.test_number, data, consent=data.get("consent") is True, daily_limit=settings.daily_limit)
            call_id = result["id"]
            if duplicate:
                return {"call": public_call(store.get(call_id)), "duplicate": True}
            # Keep the prepared services attached until a verified carrier media
            # connection consumes them. No service is shared across concurrent calls.
            prepared[call_id] = prepared.pop("speech")
            prepared["speech"] = None
        token = media_token(call_id, settings.api_token, int(time.time()) + 300)
        try:
            sid = await asyncio.to_thread(carrier.create, call_id, stream_twiml(settings.public_url, call_id, token))
            store.bind(call_id, sid)
            if store.get(call_id)["stopped"]:
                try:
                    await asyncio.to_thread(carrier.stop, sid)
                    store.stop_result(call_id, True)
                except Exception:
                    store.stop_result(call_id, False)
        except CarrierError as exc:
            store.dispatch_failed(call_id, uncertain=exc.uncertain)
            return JSONResponse({"error": str(exc), "call": public_call(store.get(call_id))}, status_code=503)
        except Exception:
            store.dispatch_failed(call_id, uncertain=True)
            return JSONResponse({"error": "Call dispatch could not be confirmed. Check this request and the carrier console before trying again.", "call": public_call(store.get(call_id))}, status_code=503)
        return {"call": public_call(store.get(call_id)), "duplicate": False}

    @app.get("/api/calls")
    async def list_calls(request: Request):
        authorized(request)
        return {"calls": [public_call(r) for r in store.list()]}

    @app.post("/api/calls/{call_id}/stop")
    async def stop(call_id: str, request: Request):
        authorized(request)
        store.stop_contact(call_id)
        r = store.get(call_id)
        if r["sid"]:
            try:
                await asyncio.to_thread(carrier.stop, r["sid"])
                store.stop_result(call_id, True)
            except Exception:
                store.stop_result(call_id, False)
        else:
            # The dispatch may still be in flight. The create response checks the
            # durable stopped flag and hangs up as soon as a call SID is known.
            store.stop_result(call_id, False)
        if call_id in sessions:
            await sessions[call_id]["close"]("stop")
        return {"call": public_call(store.get(call_id))}

    @app.post("/api/calls/{call_id}/reconcile")
    async def reconcile(call_id: str, request: Request):
        authorized(request)
        r = store.get(call_id)
        if not r["sid"]:
            data = await body(request)
            store.resolve_unknown(call_id, carrier_checked=data.get("carrier_checked") is True)
        else:
            try:
                data = await asyncio.to_thread(carrier._request, "/Calls/" + r["sid"] + ".json")
                store.status(call_id, r["sid"], data["status"], r["sequence"] + 1)
            except Exception:
                raise RuleError("Carrier reconciliation failed. No new call has been started.", 503) from None
        return {"call": public_call(store.get(call_id))}

    @app.post("/api/calls/{call_id}/tasks/{action}")
    async def task(call_id: str, action: str, request: Request):
        authorized(request)
        store.mark_task(call_id, action)
        return {"call": public_call(store.get(call_id))}

    @app.post("/api/permission")
    async def permission(request: Request):
        authorized(request)
        data = await body(request)
        store.renew_permission(settings.test_number, data.get("consent") is True)
        return {"permission_recorded": True}

    @app.post("/webhooks/status/{call_id}")
    async def carrier_status(call_id: str, request: Request):
        data = await signed_form(request)
        sid = data.get("CallSid", "")
        if data.get("AccountSid") != settings.account_sid or not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid):
            raise RuleError("Carrier account or call mismatch.", 403)
        try:
            sequence = int(data["SequenceNumber"])
        except (KeyError, TypeError, ValueError):
            raise RuleError("A valid carrier sequence number is required.", 422) from None
        store.status(call_id, sid, data.get("CallStatus", ""), sequence)
        if data.get("CallStatus") in TERMINAL:
            prepared.pop(call_id, None)
        return Response(status_code=204)

    @app.post("/webhooks/amd/{call_id}")
    async def answering_machine(call_id: str, request: Request):
        data = await signed_form(request)
        r = store.get(call_id)
        if data.get("AccountSid") != settings.account_sid or data.get("CallSid") != r["sid"]:
            raise RuleError("Carrier account or call mismatch.", 403)
        if data.get("AnsweredBy", "").startswith("machine") or data.get("AnsweredBy") == "fax":
            if r["stage"] != "closed":
                store.mutate(call_id, "voicemail")
            try:
                await asyncio.to_thread(carrier.stop, r["sid"])
            except Exception:
                store.stop_result(call_id, False)
        return Response(status_code=204)

    @app.post("/webhooks/transfer/{call_id}")
    async def transfer_result(call_id: str, request: Request):
        data = await signed_form(request)
        r = store.get(call_id)
        if data.get("AccountSid") != settings.account_sid or data.get("CallSid") != r["sid"]:
            raise RuleError("Carrier account or call mismatch.", 403)
        with store.db(True) as db:
            store._event(db, call_id, "staff_transfer_result", data.get("DialCallStatus", "unknown"))
            # A connected phone is not proof a staff member accepted task ownership.
            store._task(db, call_id, "Staff transfer ended; verify handoff and resolve the follow-up explicitly")
        return Response("<Response><Hangup/></Response>", media_type="application/xml")

    @app.websocket("/media/{call_id}")
    async def media(websocket: WebSocket, call_id: str):
        await websocket.accept()
        try:
            # Capability arrives as a Twilio Stream custom parameter, not a query
            # string that normal reverse-proxy access logs would capture.
            start = None
            async with asyncio.timeout(6):
                for _ in range(4):
                    raw = await websocket.receive_text()
                    if len(raw) > 16384:
                        raise RuleError("Oversized media handshake.", 403)
                    frame = json.loads(raw)
                    if frame.get("event") == "start":
                        start = frame["start"]
                        break
            if not start or start.get("accountSid") != settings.account_sid:
                raise RuleError("Invalid carrier media handshake.", 403)
            token = start.get("customParameters", {}).get("token", "")
            if not validate_media_token(token, call_id, settings.api_token):
                raise RuleError("Expired or invalid media capability.", 403)
            sid, stream_sid = start.get("callSid", ""), start.get("streamSid", "")
            if not re.fullmatch(r"MZ[0-9a-fA-F]{32}", stream_sid):
                raise RuleError("Invalid stream reference.", 403)
            # Media can beat the REST create response and signed status callback.
            # Only the call-bound, expiring capability permits this early binding.
            if store.get(call_id)["sid"] is None:
                store.bind(call_id, sid)
            store.claim_stream(call_id, sid)
            speech = prepared.pop(call_id, None)
            if speech is None:
                raise RuleError("The voice worker is unavailable. No automatic reconnect is allowed.", 503)
            if run_voice_fn is None:
                from .runtime import run_voice
                run = run_voice
            else:
                run = run_voice_fn
            await run(websocket, call_id, stream_sid, sid, settings, store, carrier, speech, sessions)
        except (RuleError, ValueError, KeyError, TimeoutError, WebSocketDisconnect):
            try:
                r = store.get(call_id)
                if r["stream_claimed"] and r["stage"] != "closed":
                    store.mutate(call_id, "technical")
            except RuleError:
                pass
        except Exception:
            # Do not print transcript, audio or credential-bearing exception objects.
            logging.getLogger("happysmile").error("Voice worker failed for an authenticated session.")
            try:
                store.mutate(call_id, "technical")
            except RuleError:
                pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    return app


def main():
    import uvicorn
    import sys
    from loguru import logger
    # Pipecat debug messages can include utterances. Do not enable content logs.
    logger.remove()
    def content_free_log(record):
        record["exception"] = None
        return True
    logger.add(sys.stderr, level="WARNING", format="{level}: voice-runtime event in {name}", filter=content_free_log, diagnose=False, backtrace=False)
    # No access logs: no call content or capability values should appear in logs.
    uvicorn.run(create_app(), host="0.0.0.0", port=7860, workers=1, ws_max_size=16384, access_log=False)


if __name__ == "__main__":
    main()
