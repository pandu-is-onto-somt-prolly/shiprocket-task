import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import hmac
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from types import SimpleNamespace
from uuid import uuid4

from voice_backend.core import Store, RuleError, callback_time, affirmative, safety_intent, media_token, validate_media_token
from voice_backend.guard import SpeechGuard
from voice_backend.carrier import TwilioCarrier, CarrierError, valid_signature, stream_twiml

NOW = datetime.fromisoformat('2026-11-19T10:30:00+05:30').timestamp()
FUTURE = '2026-11-20T11:00:00+05:30'
CONTEXT = {'clinic':'Indiranagar','service':'General consultation','language':'English'}
NUMBER = '+19999990101'
SECRET = 'test-secret-not-a-real-credential-' * 2
SID = 'CA' + 'a'*32


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name)/'calls.sqlite3'), SECRET)

    def tearDown(self):
        self.tmp.cleanup()

    def admit(self, **kwargs):
        result, _ = self.store.admit(str(uuid4()), NUMBER, CONTEXT, consent=True, now=NOW, **kwargs)
        return result['id']

    def confirmed_identity(self):
        call_id=self.admit()
        self.store.bind(call_id, SID)
        self.store.mutate(call_id,'identity',{'confirmed':True},now=NOW)
        return call_id

    def ready_to_confirm(self):
        call_id=self.confirmed_identity()
        self.store.mutate(call_id,'interest',CONTEXT,now=NOW)
        self.store.mutate(call_id,'preference',{'date_time':FUTURE},now=NOW)
        return call_id

    def test_explicit_consent_required(self):
        with self.assertRaises(RuleError):self.store.admit(str(uuid4()),NUMBER,CONTEXT,consent=False,now=NOW)
        self.assertEqual(self.store.list(),[])

    def test_bad_request_id_rejected(self):
        with self.assertRaises(RuleError):self.store.admit('not-uuid',NUMBER,CONTEXT,consent=True,now=NOW)

    def test_unknown_clinic_rejected(self):
        with self.assertRaises(RuleError):self.store.admit(str(uuid4()),NUMBER,{**CONTEXT,'clinic':'unknown'},consent=True,now=NOW)

    def test_malformed_selections_are_validation_errors(self):
        for bad in [[], {}, None, 3]:
            with self.assertRaises(RuleError):self.store.admit(str(uuid4()),NUMBER,{**CONTEXT,'clinic':bad},consent=True,now=NOW)
        self.assertEqual(self.store.list(),[])

    def test_live_language_support_is_honest(self):
        with self.assertRaises(RuleError):self.store.admit(str(uuid4()),NUMBER,{**CONTEXT,'language':'Kannada'},consent=True,now=NOW)

    def test_real_clock_blocks_night_calls(self):
        night=datetime.fromisoformat('2026-11-19T23:00:00+05:30').timestamp()
        with self.assertRaises(RuleError):self.store.admit(str(uuid4()),NUMBER,CONTEXT,consent=True,now=night)

    def test_cooldown_applies_even_after_a_failed_call(self):
        call_id=self.admit();self.store.dispatch_failed(call_id,uncertain=False)
        with self.assertRaises(RuleError):self.store.admit(str(uuid4()),NUMBER,CONTEXT,consent=True,now=NOW+60)

    def test_daily_cap_applies_after_cooldown_expires(self):
        call_id=self.admit();self.store.dispatch_failed(call_id,uncertain=False)
        with self.assertRaises(RuleError):self.store.admit(str(uuid4()),NUMBER,CONTEXT,consent=True,now=NOW+181,daily_limit=1)

    def test_repeated_request_has_one_dispatch_record(self):
        key=str(uuid4())
        first,_=self.store.admit(key,NUMBER,CONTEXT,consent=True,now=NOW)
        second,duplicate=self.store.admit(key,NUMBER,CONTEXT,consent=True,now=NOW)
        self.assertEqual(first['id'],second['id']);self.assertTrue(duplicate);self.assertEqual(len(self.store.list()),1)

    def test_concurrent_distinct_clicks_admit_only_one_call(self):
        barrier=threading.Barrier(6)
        def attempt(_):
            barrier.wait()
            try:self.admit();return True
            except RuleError:return False
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,range(6)))
        self.assertEqual(sum(results),1)

    def test_database_stores_mask_and_hash_not_phone(self):
        call_id=self.admit();record=self.store.get(call_id)
        self.assertEqual(record['last4'],'0101');self.assertNotIn(NUMBER, json.dumps(record))
        self.assertNotIn(NUMBER.encode(),Path(self.store.path).read_bytes())

    def test_unknown_dispatch_blocks_redial(self):
        call_id=self.admit();self.store.dispatch_failed(call_id,uncertain=True)
        with self.assertRaises(RuleError):self.admit(cooldown=0)
        self.assertIn('do not redial',self.store.get(call_id)['task']['reason'])

    def test_unknown_dispatch_requires_operator_carrier_check(self):
        call_id=self.admit();self.store.dispatch_failed(call_id,uncertain=True)
        with self.assertRaises(RuleError):self.store.resolve_unknown(call_id,carrier_checked=False)
        self.store.resolve_unknown(call_id,carrier_checked=True)
        self.assertEqual(self.store.get(call_id)['status'],'failed')

    def test_crash_during_create_is_recovered_without_redial(self):
        call_id=self.admit();Store(self.store.path,SECRET).recover(now=NOW+400)
        self.assertEqual(self.store.get(call_id)['status'],'dispatch_unknown')

    def test_binding_does_not_resurrect_earlier_terminal_webhook(self):
        call_id=self.admit();self.store.status(call_id,SID,'completed',4);self.store.bind(call_id,SID)
        self.assertEqual(self.store.get(call_id)['status'],'completed')

    def test_duplicate_and_late_statuses_do_not_resurrect_call(self):
        call_id=self.admit();self.store.bind(call_id,SID)
        self.assertTrue(self.store.status(call_id,SID,'completed',4))
        self.assertFalse(self.store.status(call_id,SID,'ringing',2))
        self.assertFalse(self.store.status(call_id,SID,'in-progress',5))
        self.assertEqual(self.store.get(call_id)['status'],'completed')

    def test_status_from_another_carrier_call_is_rejected(self):
        call_id=self.admit();self.store.bind(call_id,SID)
        with self.assertRaises(RuleError):self.store.status(call_id,'CA'+'b'*32,'completed',4)

    def test_media_connection_is_single_use_and_bound_to_sid(self):
        call_id=self.admit();self.store.bind(call_id,SID)
        with self.assertRaises(RuleError):self.store.claim_stream(call_id,'CA'+'b'*32)
        self.store.claim_stream(call_id,SID)
        with self.assertRaises(RuleError):self.store.claim_stream(call_id,SID)

    def test_stop_before_media_blocks_connection(self):
        call_id=self.admit();self.store.bind(call_id,SID);self.store.stop_contact(call_id)
        with self.assertRaises(RuleError):self.store.claim_stream(call_id,SID)

    def test_stop_suppression_survives_restart(self):
        call_id=self.admit();self.store.stop_contact(call_id);self.store.dispatch_failed(call_id,uncertain=False)
        self.store=Store(self.store.path,SECRET)
        with self.assertRaises(RuleError):self.admit(cooldown=0)

    def test_new_permission_is_explicit_and_does_not_itself_dial(self):
        call_id=self.admit();self.store.stop_contact(call_id)
        with self.assertRaises(RuleError):self.store.renew_permission(NUMBER,False)
        self.store.renew_permission(NUMBER,True)
        self.assertEqual(len(self.store.list()),1)

    def test_mutations_after_stop_cannot_create_an_appointment_request(self):
        call_id=self.ready_to_confirm();revision=self.store.get(call_id)['revision'];self.store.stop_contact(call_id)
        with self.assertRaises(RuleError):self.store.mutate(call_id,'submit',{'confirmed':True,'revision':revision},now=NOW)

    def test_late_llm_mutation_after_disconnect_is_rejected(self):
        call_id=self.ready_to_confirm();revision=self.store.get(call_id)['revision'];self.store.status(call_id,SID,'completed',4)
        with self.assertRaises(RuleError):self.store.mutate(call_id,'submit',{'confirmed':True,'revision':revision},now=NOW)

    def test_interest_cannot_be_collected_before_identity(self):
        call_id=self.admit()
        with self.assertRaises(RuleError):self.store.mutate(call_id,'interest',CONTEXT,now=NOW)

    def test_appointment_request_requires_current_readback_revision(self):
        call_id=self.ready_to_confirm();revision=self.store.get(call_id)['revision']
        with self.assertRaises(RuleError):self.store.mutate(call_id,'submit',{'confirmed':True,'revision':revision-1},now=NOW)
        r=self.store.mutate(call_id,'submit',{'confirmed':True,'revision':revision},now=NOW)
        self.assertEqual(r['outcome'],'appointment_requested');self.assertIn('no booking exists',r['task']['reason']);self.assertNotIn('booking_reference',r['details'])

    def test_interest_correction_discards_stale_time(self):
        call_id=self.ready_to_confirm();self.store.mutate(call_id,'interest',{'clinic':'Whitefield','service':'Dental implants'},now=NOW)
        r=self.store.get(call_id);self.assertEqual(r['stage'],'preference');self.assertNotIn('appointment_preference',r['details'])

    def test_repeated_submit_cannot_duplicate_staff_task(self):
        call_id=self.ready_to_confirm();revision=self.store.get(call_id)['revision']
        self.store.mutate(call_id,'submit',{'confirmed':True,'revision':revision},now=NOW)
        with self.assertRaises(RuleError):self.store.mutate(call_id,'submit',{'confirmed':True,'revision':revision},now=NOW)
        with self.store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)

    def test_callback_requires_identity_time_and_confirmation(self):
        call_id=self.confirmed_identity();revision=self.store.get(call_id)['revision']
        with self.assertRaises(RuleError):self.store.mutate(call_id,'callback',{'date_time':FUTURE},now=NOW)
        r=self.store.mutate(call_id,'callback',{'date_time':FUTURE,'confirmed':True,'revision':revision},now=NOW)
        self.assertEqual(r['outcome'],'callback_requested');self.assertIn('no automatic redial',r['task']['reason'])

    def test_no_answer_does_not_automatically_retry(self):
        call_id=self.admit();self.store.bind(call_id,SID);self.store.status(call_id,SID,'no-answer',2)
        self.assertEqual(len(self.store.list()),1);self.assertIsNotNone(self.store.get(call_id)['task'])

    def test_human_handoff_creates_task_before_any_transfer(self):
        call_id=self.confirmed_identity();r=self.store.mutate(call_id,'human',now=NOW)
        self.assertEqual(r['outcome'],'staff_followup');self.assertIsNone(r['task']['owner'])

    def test_urgent_concern_gets_urgent_task(self):
        call_id=self.confirmed_identity();r=self.store.mutate(call_id,'urgent',now=NOW)
        self.assertEqual(r['task']['priority'],'urgent')

    def test_transfer_update_does_not_downgrade_urgent_task(self):
        call_id=self.confirmed_identity();self.store.mutate(call_id,'urgent',now=NOW)
        with self.store.db(True) as db:self.store._task(db,call_id,'Staff transfer ended; verify handoff')
        self.assertEqual(self.store.get(call_id)['task']['priority'],'urgent')

    def test_staff_task_cannot_be_resolved_without_claim(self):
        call_id=self.confirmed_identity();self.store.mutate(call_id,'human',now=NOW)
        with self.assertRaises(RuleError):self.store.mark_task(call_id,'resolve')
        self.store.mark_task(call_id,'claim');self.store.mark_task(call_id,'resolve')
        with self.assertRaises(RuleError):self.store.mark_task(call_id,'resolve')

    def test_contact_stop_cancels_outreach_instruction(self):
        call_id=self.confirmed_identity();self.store.mutate(call_id,'human',now=NOW);self.store.stop_contact(call_id)
        self.assertTrue(self.store.get(call_id)['task']['resolved'])

    def test_unconfirmed_hangup_is_visible_and_actionable(self):
        call_id=self.admit();self.store.stop_contact(call_id);self.store.stop_result(call_id,False)
        r=self.store.get(call_id);self.assertTrue(r['stop_pending']);self.assertEqual(r['task']['priority'],'urgent')

    def test_signed_terminal_status_clears_hangup_uncertainty(self):
        call_id=self.admit();self.store.bind(call_id,SID);self.store.stop_contact(call_id);self.store.stop_result(call_id,False)
        self.store.status(call_id,SID,'completed',3)
        self.assertFalse(self.store.get(call_id)['stop_pending'])

    def test_hangup_failure_preserves_original_urgent_concern(self):
        call_id=self.confirmed_identity();self.store.mutate(call_id,'urgent',now=NOW);self.store.stop_result(call_id,False)
        r=self.store.get(call_id);self.assertIn('Urgent clinical concern',r['task']['reason']);self.assertIn('hangup unconfirmed',r['task']['reason']);self.assertFalse(r['stopped'])


class SpeechGuardTests(unittest.TestCase):
    def test_old_yes_cannot_confirm_new_readback(self):
        g=SpeechGuard();g.user_text('yes');g.arm_readback(3,'appointment');g.bot_started();g.bot_stopped()
        self.assertFalse(g.can_confirm(3,'appointment'))

    def test_fresh_yes_after_full_readback_is_required(self):
        g=SpeechGuard();g.arm_readback(3,'appointment');g.bot_started();g.bot_stopped();g.user_text('yes')
        self.assertTrue(g.can_confirm(3,'appointment'));self.assertFalse(g.can_confirm(4,'appointment'));self.assertFalse(g.can_confirm(3,'callback'))

    def test_barge_in_invalidates_confirmation(self):
        g=SpeechGuard();g.arm_readback(3,'appointment');g.bot_started();g.user_started();g.user_text('yes');g.bot_stopped()
        self.assertFalse(g.can_confirm(3,'appointment'))

    def test_yes_before_audio_starts_cannot_confirm(self):
        g=SpeechGuard();g.arm_readback(3,'appointment');g.user_started();g.user_text('yes');g.bot_started();g.bot_stopped()
        self.assertFalse(g.can_confirm(3,'appointment'))

    def test_transcription_during_readback_rejects_yes_without_vad(self):
        g=SpeechGuard();g.arm_readback(3,'appointment');g.bot_started();g.user_text('yes');g.bot_stopped()
        self.assertFalse(g.can_confirm(3,'appointment'))

    def test_correction_clears_confirmation(self):
        g=SpeechGuard();g.arm_readback(3,'appointment');g.bot_started();g.bot_stopped();g.user_text('yes');g.changed()
        self.assertFalse(g.can_confirm(3,'appointment'))

    def test_silence_and_repair_budgets_are_bounded(self):
        g=SpeechGuard();self.assertEqual([g.idle(),g.idle(),g.idle()],['remind','remind','end']);self.assertEqual([g.repair(),g.repair(),g.repair()],[True,True,False])

    def test_ambiguous_confirmation_is_not_yes(self):
        for text in ['maybe','no','yes but change the date','I guess','not confirmed']:
            self.assertFalse(affirmative(text))

    def test_priority_intents(self):
        for phrase,intent in [('stop calling me','stop'),('you have the wrong person','wrong_person'),('I want to speak to a human','human'),('I cannot breathe','urgent')]:self.assertEqual(safety_intent(phrase),intent)

    def test_short_and_smart_apostrophe_optouts(self):
        for text in ['Stop!','hang up','please stop','don\u2019t call me again']:
            self.assertEqual(safety_intent(text),'stop')

    def test_time_validation_rejects_ambiguous_past_and_closed_hours(self):
        for value in [None, [], 12, 'tomorrow morning','2026-11-20T11:00:00','2026-11-18T11:00:00+05:30','2026-11-20T22:00:00+05:30']:
            with self.assertRaises(RuleError):callback_time(value,NOW)


class TransportTests(unittest.TestCase):
    def test_media_capability_is_expiring_and_call_bound(self):
        call_id=str(uuid4());token=media_token(call_id,SECRET,int(NOW)+30)
        self.assertTrue(validate_media_token(token,call_id,SECRET,NOW));self.assertFalse(validate_media_token(token,call_id,SECRET,NOW+31));self.assertFalse(validate_media_token(token,str(uuid4()),SECRET,NOW));self.assertFalse(validate_media_token(token+'x',call_id,SECRET,NOW))

    def test_unsigned_and_tampered_webhooks_fail(self):
        url='https://backend.example/webhooks/status/abc';pairs=[('CallStatus','ringing'),('CallSid',SID)]
        payload=url+'CallSid'+SID+'CallStatusringing'
        signature=base64.b64encode(hmac.new(SECRET.encode(),payload.encode(),hashlib.sha1).digest()).decode()
        self.assertTrue(valid_signature(url,pairs,signature,SECRET));self.assertFalse(valid_signature(url,pairs,'',SECRET));self.assertFalse(valid_signature(url,[('CallStatus','completed'),('CallSid',SID)],signature,SECRET));self.assertFalse(valid_signature(url+'x',pairs,signature,SECRET))

    def test_stream_xml_escapes_capability_and_contains_hangup_fallback(self):
        text=stream_twiml('https://backend.example','call','token&value')
        self.assertIn('token&amp;value',text);self.assertIn('<Hangup',text);self.assertNotIn(SECRET,text)

    def test_carrier_create_always_uses_server_configured_destination(self):
        captured=[]
        def opener(request,timeout):
            captured.append(request);return io.BytesIO(json.dumps({'sid':SID}).encode())
        s=SimpleNamespace(account_sid='AC'+'b'*32,auth_token=SECRET,test_number=NUMBER,from_number='+19999990202',max_seconds=180,public_url='https://backend.example',amd=True)
        self.assertEqual(TwilioCarrier(s,opener).create('call','<Response/>'),SID)
        fields=parse_qs(captured[0].data.decode());self.assertEqual(fields['To'],[NUMBER]);self.assertEqual(fields['TimeLimit'],['180']);self.assertEqual(fields['AsyncAmd'],['true']);self.assertNotIn('Record',fields)

    def test_upstream_timeout_is_uncertain_not_safe_to_retry(self):
        def opener(*args,**kwargs):raise URLError('test timeout')
        s=SimpleNamespace(account_sid='AC'+'b'*32,auth_token=SECRET)
        with self.assertRaises(CarrierError) as result:TwilioCarrier(s,opener)._request('/Calls.json',{})
        self.assertTrue(result.exception.uncertain)

    def test_upstream_definite_rejection_does_not_claim_a_call_was_placed(self):
        def opener(request,timeout):raise HTTPError(request.full_url,400,'rejected',{},None)
        s=SimpleNamespace(account_sid='AC'+'b'*32,auth_token=SECRET)
        with self.assertRaises(CarrierError) as result:TwilioCarrier(s,opener)._request('/Calls.json',{})
        self.assertFalse(result.exception.uncertain)


if __name__ == '__main__':
    unittest.main()
