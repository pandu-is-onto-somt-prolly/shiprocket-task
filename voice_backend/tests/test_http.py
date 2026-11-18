"""Run inside the installed backend environment; no real carrier calls are made."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import urlencode

AVAILABLE = bool(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'))


@unittest.skipUnless(AVAILABLE, 'FastAPI/httpx are not installed in this authoring environment; run inside the backend container.')
class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx
        from voice_backend.config import Settings
        from voice_backend.app import create_app
        self.tmp=tempfile.TemporaryDirectory()
        self.created=0
        test=self
        class FakeCarrier:
            def create(self,call_id,twiml):test.created+=1;return 'CA'+'a'*32
            def stop(self,sid):pass
            def _request(self,path):return {'status':'completed'}
        async def prepare(settings):return (object(),object())
        self.settings=Settings(api_token='t'*40,public_url='https://backend.example',account_sid='AC'+'b'*32,auth_token='not-a-real-token',from_number='+19999990202',test_number='+19999990101',allowed_origins=('https://frontend.example',),database=str(Path(self.tmp.name)/'db.sqlite3'),enabled=True)
        self.app=create_app(self.settings,FakeCarrier(),warmup_fn=prepare)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='https://backend.example')
        self.headers={'Authorization':'Bearer '+'t'*40,'Origin':'https://frontend.example'}
        self.context={'clinic':'Indiranagar','service':'General consultation','language':'English','consent':True}
        self.clock=patch('time.time',return_value=datetime.fromisoformat('2026-11-19T10:30:00+05:30').timestamp());self.clock.start()

    async def asyncTearDown(self):
        await self.client.aclose();self.clock.stop();self.tmp.cleanup()

    async def test_config_does_not_expose_credentials_or_phone(self):
        response=await self.client.get('/api/config',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertNotIn(self.settings.api_token,response.text);self.assertNotIn(self.settings.test_number,response.text);self.assertNotIn(self.settings.auth_token,response.text)

    async def test_unauthenticated_dashboard_is_rejected(self):
        self.assertEqual((await self.client.get('/api/calls')).status_code,401)

    async def test_disallowed_origin_is_rejected_even_with_token(self):
        response=await self.client.get('/api/config',headers={**self.headers,'Origin':'https://other.example'})
        self.assertEqual(response.status_code,403)

    async def test_no_call_without_preparing_models(self):
        response=await self.client.post('/api/calls',headers={**self.headers,'Idempotency-Key':str(uuid4())},json=self.context)
        self.assertEqual(response.status_code,503);self.assertEqual(self.created,0)

    async def test_destination_injection_is_rejected(self):
        response=await self.client.post('/api/calls',headers=self.headers,json={**self.context,'to':'+19999990303'})
        self.assertEqual(response.status_code,422);self.assertEqual(self.created,0)

    async def test_double_post_creates_only_one_carrier_call(self):
        await self.client.post('/api/prepare',headers=self.headers,json={})
        headers={**self.headers,'Idempotency-Key':str(uuid4())}
        first=await self.client.post('/api/calls',headers=headers,json=self.context)
        second=await self.client.post('/api/calls',headers=headers,json=self.context)
        self.assertEqual(first.status_code,200);self.assertEqual(second.status_code,200);self.assertEqual(self.created,1);self.assertTrue(second.json()['duplicate'])

    async def test_unsigned_webhook_cannot_change_status(self):
        await self.client.post('/api/prepare',headers=self.headers,json={})
        result=await self.client.post('/api/calls',headers={**self.headers,'Idempotency-Key':str(uuid4())},json=self.context)
        call_id=result.json()['call']['id']
        response=await self.client.post('/webhooks/status/'+call_id,content=urlencode({'AccountSid':self.settings.account_sid,'CallSid':'CA'+'a'*32,'SequenceNumber':'1','CallStatus':'completed'}),headers={'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(response.status_code,403);self.assertEqual(self.app.state.store.get(call_id)['status'],'queued')

    async def test_oversize_body_is_rejected_before_carrier_request(self):
        response=await self.client.post('/api/calls',headers=self.headers,json={'padding':'x'*20000})
        self.assertEqual(response.status_code,413);self.assertEqual(self.created,0)
