"""Twilio REST transport and signed-webhook validation, using stdlib HTTP."""
import base64
import hashlib
import hmac
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, tostring

from .core import RuleError


class CarrierError(Exception):
    def __init__(self, uncertain: bool, message="Carrier request failed; check the carrier console."):
        super().__init__(message)
        self.uncertain = uncertain


def valid_signature(url: str, pairs: list[tuple[str, str]], signature: str, secret: str) -> bool:
    # Twilio's form webhook signature covers the full configured public URL and
    # each sorted key/value. Keep all fields, including future provider additions.
    fields = {}
    for key, value in pairs:
        fields.setdefault(key, set()).add(value)
    payload = url + "".join(key + value for key in sorted(fields) for value in sorted(fields[key]))
    expected = base64.b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


def stream_twiml(public_url: str, call_id: str, token: str) -> str:
    root = Element("Response")
    stream = SubElement(SubElement(root, "Connect"), "Stream", {"url": public_url.replace("https://", "wss://", 1) + "/media/" + call_id})
    SubElement(stream, "Parameter", {"name": "token", "value": token})
    # A broken media stream ends the call rather than silently leaving a person waiting.
    SubElement(root, "Hangup")
    return tostring(root, encoding="unicode")


def transfer_twiml(public_url: str, call_id: str, number: str) -> str:
    root = Element("Response")
    dial = SubElement(root, "Dial", {"timeout": "15", "timeLimit": "120", "action": public_url + "/webhooks/transfer/" + call_id, "method": "POST"})
    SubElement(dial, "Number").text = number
    SubElement(root, "Hangup")
    return tostring(root, encoding="unicode")


class TwilioCarrier:
    def __init__(self, settings, opener=urlopen):
        self.settings, self.opener = settings, opener

    def _request(self, path, data=None):
        credentials = base64.b64encode(f"{self.settings.account_sid}:{self.settings.auth_token}".encode()).decode()
        req = Request("https://api.twilio.com/2010-04-01/Accounts/" + self.settings.account_sid + path,
                      data=urlencode(data, doseq=True).encode() if data is not None else None,
                      headers={"Authorization": "Basic " + credentials, "Content-Type": "application/x-www-form-urlencoded"},
                      method="POST" if data is not None else "GET")
        try:
            with self.opener(req, timeout=12) as response:
                return json.loads(response.read(1024 * 1024))
        except HTTPError as exc:
            # A timeout or server error does not prove a mutation was not accepted.
            raise CarrierError(exc.code >= 500 or exc.code == 408) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise CarrierError(True) from None

    def create(self, call_id, twiml):
        data = {"To": self.settings.test_number, "From": self.settings.from_number,
                "Twiml": twiml, "Timeout": "25", "TimeLimit": str(self.settings.max_seconds),
                "StatusCallback": self.settings.public_url + "/webhooks/status/" + call_id,
                "StatusCallbackMethod": "POST", "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"]}
        if self.settings.amd:
            data.update(MachineDetection="Enable", AsyncAmd="true", AsyncAmdStatusCallback=self.settings.public_url + "/webhooks/amd/" + call_id, AsyncAmdStatusCallbackMethod="POST")
        result = self._request("/Calls.json", data)
        sid = result.get("sid", "")
        if not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid):
            raise CarrierError(True, "The carrier response was incomplete; reconcile before retrying.")
        return sid

    def stop(self, sid):
        if not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid or ""):
            raise CarrierError(True)
        details = self._request("/Calls/" + sid + ".json")
        if details.get("status") in {"completed", "canceled", "failed", "busy", "no-answer"}:
            return
        target = "canceled" if details.get("status") in {"queued", "ringing", "initiated"} else "completed"
        self._request("/Calls/" + sid + ".json", {"Status": target})

    def transfer(self, sid, call_id):
        if not self.settings.staff_number:
            return False
        self._request("/Calls/" + sid + ".json", {"Twiml": transfer_twiml(self.settings.public_url, call_id, self.settings.staff_number)})
        return True
