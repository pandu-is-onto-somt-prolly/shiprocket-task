// The operator token lives only in this page's memory. It is never stored or bundled.
const byId = id => document.getElementById(id);
const html = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let endpoint = '', accessToken = '', configuration = null, callKey = crypto.randomUUID(), pollTimer = null, inFlight = false;
let liveCalls = [];
function feedback(message, error=false) {byId('voice-feedback').textContent=message;byId('live-workspace-feedback').textContent=message;byId('live-workspace-feedback').classList.toggle('error',error);byId('voice-feedback').classList.toggle('error',error);}
async function request(path, {method='GET',data,headers={}}={}) {
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),path==='/api/prepare'?190000:25000);
  try {
    const result=await fetch(endpoint+path,{method,headers:{'Authorization':'Bearer '+accessToken,'Content-Type':'application/json',...headers},body:data===undefined?undefined:JSON.stringify(data),signal:controller.signal,cache:'no-store',credentials:'omit',redirect:'error'});
    const payload=await result.json();
    if(!result.ok){if(payload.call)refresh();throw new Error(payload.error||'The backend could not complete this request.');}
    return payload;
  } finally {clearTimeout(timer);}
}
function busy(on){inFlight=on;for(const id of ['voice-prepare','voice-call','voice-renew'])byId(id).disabled=on;}
function readable(value){return String(value||'Pending').replaceAll('_',' ');}
function when(seconds){return new Date(seconds*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'})+' IST';}
function render(){
  byId('live-workspace').hidden=!configuration;
  byId('voice-connection-state').textContent=configuration?`Connected · test phone ending ${configuration.test_last4} · English`:'Backend not connected';
  byId('voice-start-controls').hidden=!configuration;
  if(configuration)byId('voice-prepare').textContent=configuration.prepared?'Voice models prepared':'Prepare local voice models';
  const active=liveCalls.find(c=>['creating','dispatch_unknown','queued','initiated','ringing','in-progress'].includes(c.status));
  byId('voice-call').disabled=inFlight||!configuration?.prepared||!!active;
  byId('voice-active').textContent=active?`Current real call: ${readable(active.status)}. Closing this page does not hang up your phone.`:'No active real call shown. Refresh status if a launch response was lost.';
  byId('voice-stop').hidden=!active;
  byId('live-calls-list').innerHTML=liveCalls.length?liveCalls.map(call=>`<article class="live-call-row"><div class="live-call-top"><strong>Phone ending ${html(call.last4)}</strong><span class="status-badge ${call.status==='dispatch_unknown'?'amber':'blue'}">${html(readable(call.status))}</span></div><p>${html(when(call.created))} · ${html(call.id.slice(0,8))} · ${html(call.details.clinic)}</p><p><strong>Outcome:</strong> ${html(readable(call.outcome))}${call.outcome==='appointment_requested'?' · Clinic confirmation still required.':''}</p>${call.details.appointment_preference?`<p>Appointment preference: ${html(call.details.appointment_preference)}</p>`:''}${call.details.callback_preference?`<p>Callback preference: ${html(call.details.callback_preference)} · Staff review required.</p>`:''}${call.stopped?'<p class="live-warning">Contact stopped. No new calls are permitted without fresh owner permission.</p>':''}${call.stop_pending?'<p class="live-warning">Carrier hangup is unconfirmed. Hang up the phone and check the carrier console before any new call.</p>':''}${call.task?`<div class="live-task"><strong>${html(call.task.priority==='urgent'?'Urgent staff attention':'Staff follow-up')}</strong><p>${html(call.task.reason)}</p><small>${html(call.task.owner||'Unassigned')} · ${call.task.resolved?'Resolved':'Due '+html(when(call.task.due))}</small></div>`:''}<div class="live-call-actions">${(!call.stopped||call.stop_pending)?`<button class="button danger" data-live-action="stop" data-id="${call.id}">${call.stop_pending?'Retry ending call':'Stop further contact'}</button>`:''}${call.task&&!call.task.resolved?`<button class="button secondary" data-live-action="${call.task.owner?'resolve':'claim'}" data-id="${call.id}">${call.task.owner?'Resolve staff task':'Claim staff task'}</button>`:''}<button class="button secondary" data-live-action="reconcile" data-id="${call.id}">Check carrier status</button></div>${call.status==='dispatch_unknown'?`<label class="live-attest"><input type="checkbox" data-attest="${call.id}">I checked the carrier console and verified there is no active call.</label><button class="text-button" data-live-action="clear-unknown" data-id="${call.id}">Clear reconciled dispatch</button>`:''}<details class="live-events"><summary>Call activity</summary><ol>${call.events.map(e=>`<li>${html(readable(e.kind))}${e.detail?': '+html(e.detail):''}</li>`).join('')}</ol></details></article>`).join(''):'<p class="live-empty">No real calls yet. Start a consented test call from the patient screen.</p>';
}
async function refresh(){
  if(!configuration)return;
  try {const data=await request('/api/calls');liveCalls=data.calls;render();}
  catch(error){feedback('Status connection lost. A phone call may still be active. Reconnect or check the carrier console; do not redial blindly.',true);}
}
byId('voice-connect').addEventListener('submit',async event=>{
  event.preventDefault();
  try {
    const url=new URL(byId('voice-url').value.trim());
    if(url.username||url.password||url.search||url.hash||!['','/'].includes(url.pathname)||!(url.protocol==='https:'||url.protocol==='http:'&&['127.0.0.1','localhost'].includes(url.hostname)))throw new Error('Use the HTTPS origin of your own voice backend, or localhost for development.');
    endpoint=url.origin;accessToken=byId('voice-token').value.trim();
    if(accessToken.length<32)throw new Error('Enter the backend access token you configured; at least 32 characters.');
    configuration=await request('/api/config');byId('voice-token').value='';
    feedback(configuration.enabled?'Connected. Prepare the local voice models, then explicitly start a test call.':'Connected, but live calling is disabled in backend configuration.');
    clearInterval(pollTimer);pollTimer=setInterval(refresh,5000);await refresh();render();
  }catch(error){configuration=null;clearInterval(pollTimer);feedback(error.message||'Could not connect to the backend.',true);render();}
});
byId('voice-prepare').addEventListener('click',async()=>{
  busy(true);feedback('Preparing local speech models and checking Ollama tool support. The first run downloads model files. No phone is dialled yet.');
  try {await request('/api/prepare',{method:'POST',data:{}});configuration.prepared=true;feedback('Local models are prepared. You can now start a real test call.');}
  catch(error){configuration.prepared=false;feedback(error.message||'Voice preparation failed. No phone was dialled.',true);}
  finally{busy(false);render();}
});
byId('voice-call').addEventListener('click',async()=>{
  if(inFlight||!configuration)return;
  if(!byId('voice-consent').checked){feedback('Confirm that you own the configured test phone and want this real AI call.',true);return;}
  busy(true);feedback('Starting one real call to the configured test phone. Please answer your phone.');
  try {
    const result=await request('/api/calls',{method:'POST',headers:{'Idempotency-Key':callKey},data:{clinic:byId('clinic').value,service:byId('treatment').value,language:'English',consent:true}});
    feedback(`Call ${result.call.id.slice(0,8)}: ${readable(result.call.status)}. Answer the phone; tell the agent your answers naturally.`);
    // New keys are issued only after a confirmed accepted response; uncertain
    // requests retain their key and server admission still blocks duplicates.
    callKey=crypto.randomUUID();configuration.prepared=false;await refresh();
  }catch(error){feedback((error.message||'The response was lost.')+' The call may have started. Refresh status before trying again.',true);await refresh();}
  finally{byId('voice-consent').checked=false;busy(false);render();}
});
byId('voice-stop').addEventListener('click',async()=>{
  const active=liveCalls.find(c=>['creating','dispatch_unknown','queued','initiated','ringing','in-progress'].includes(c.status));
  if(!active)return;
  try {await request(`/api/calls/${active.id}/stop`,{method:'POST',data:{}});byId('voice-consent').checked=false;feedback('Further contact is suppressed. Check status to confirm the carrier ended the active call.');await refresh();}
  catch(error){feedback('Hangup is unconfirmed. Hang up your phone and check the carrier console.',true);}
});
byId('voice-refresh').addEventListener('click',refresh);
byId('voice-renew').addEventListener('click',async()=>{
  if(!byId('voice-consent').checked){feedback('Tick the test-phone permission box again to record fresh permission.',true);return;}
  try {await request('/api/permission',{method:'POST',data:{consent:true}});feedback('New permission for the configured test phone was recorded. This does not start a call.');}
  catch(error){feedback(error.message,true);}
});
byId('live-calls-list').addEventListener('click',async event=>{
  const button=event.target.closest('[data-live-action]');if(!button)return;
  const {liveAction:action,id}=button.dataset;button.disabled=true;
  try {
    if(action==='clear-unknown'){
      if(!document.querySelector(`[data-attest="${id}"]`)?.checked)throw new Error('Verify the carrier console and tick the confirmation before clearing an uncertain dispatch.');
      await request(`/api/calls/${id}/reconcile`,{method:'POST',data:{carrier_checked:true}});
    }else if(action==='claim'||action==='resolve')await request(`/api/calls/${id}/tasks/${action}`,{method:'POST',data:{}});
    else if(action==='stop'){await request(`/api/calls/${id}/stop`,{method:'POST',data:{}});byId('voice-consent').checked=false;}
    else await request(`/api/calls/${id}/reconcile`,{method:'POST',data:{}});
    feedback('Live call record updated.');await refresh();
  }catch(error){feedback(error.message,true);button.disabled=false;}
});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
render();
