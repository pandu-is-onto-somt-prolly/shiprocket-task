import {createState,submitRequest,startCall,connectCall,finishCall,staffAction,filterEntries,stats,STATUS,ATTENTION,dayAfter,validateSchedule} from './model.mjs';

const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons={
  clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2m1-15a3 3 0 0 1 0 6m3 9v-2a6 6 0 0 0-2-4"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9S4 17 4 12V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  building:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1m-5 10v-5h4v5"/>',
  inbox:'<path d="M4 4h16v16H4zM4 13h5l2 3h2l2-3h5"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-14 4h3m4 0h3"/>',
  phone:'<path d="m8 3-4 2c-2 6 9 17 15 15l2-4-5-3-2 3-6-6 3-2-3-5Z"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  alert:'<path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3h.01"/>',
  sparkle:'<path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>',
};
function icon(name){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.check}</svg>`;}
$$('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));

let state=createState();
let view=location.hash==='#clinic'?'clinic':'patient';
let selected='HS-1048';
let filter='attention';
let clinicFilter='all';
let query='';
let patientId=null;
let requestKey=makeKey();
let submitting=false;
let generation=0;
let toastTimer;
let scheduleOpen=null;
const timers=new Set();

function makeKey(){return globalThis.crypto?.randomUUID?.()||`demo-${Date.now()}-${Math.random().toString(36).slice(2)}`;}
function notify(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4200);$('#live-status').textContent=message;}
function dateLabel(day,options={}){return new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',...options}).format(new Date(`${day}T12:00:00+05:30`));}
function scheduleLabel(value){if(!value)return 'Within 5 demo minutes';return new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',hour:'numeric',minute:'2-digit',hour12:true}).format(new Date(value))+' IST';}
function badge(record){const status=STATUS[record.status];return `<span class="status-badge ${status.color}">${escape(status.label)}</span>`;}
function avatar(r){return `<span class="patient-avatar ${r.color}">${escape(r.initials)}</span>`;}
function currentPatient(){return state.entries.find(r=>r.id===patientId);}
function showView(next,{focus=false,hash=true}={}) {
  view=next==='clinic'?'clinic':'patient';
  $('#patient-screen').hidden=view!=='patient';$('#clinic-screen').hidden=view!=='clinic';
  $$('[data-view]').forEach(button=>{button.classList.toggle('active',button.dataset.view===view);button.setAttribute('aria-pressed',String(button.dataset.view===view));});
  if(hash) history.replaceState(null,'',`#${view}`);
  if(view==='clinic'){$('#new-lead').hidden=true;renderWorkspace();}
  if(focus){$('#main').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
}
$$('[data-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view,{focus:true})));
window.addEventListener('hashchange',()=>showView(location.hash==='#clinic'?'clinic':'patient',{hash:false}));
$('.brand').addEventListener('click',event=>{event.preventDefault();showView('patient',{focus:true});});

function getInput(){const form=new FormData($('#request-form'));return {name:form.get('name'),phone:form.get('phone'),clinic:form.get('clinic'),service:form.get('service'),language:form.get('language'),when:form.get('when'),date:form.get('date'),time:form.get('time'),consent:form.has('consent')};}
function clearErrors(){$$('.field-error').forEach(el=>el.textContent='');$$('[aria-invalid]').forEach(el=>el.removeAttribute('aria-invalid'));$('#form-feedback').hidden=true;}
function renderErrors(errors){clearErrors();const map={name:['#name-error','#patient-name'],phone:['#phone-error','#patient-phone'],consent:['#consent-error','#contact-consent'],schedule:['#schedule-error','#callback-date']};let first;
  for(const [key,message] of Object.entries(errors)){if(map[key]){const [err,field]=map[key];$(err).textContent=message;$(field).setAttribute('aria-invalid','true');first??=$(field);}else{$('#form-feedback').textContent=message;$('#form-feedback').hidden=false;}}
  first?.focus();
}
function setScheduleDefaults(){$('#callback-date').min=state.day;$('#callback-date').max=dayAfter(state.day,30);$('#callback-date').value=state.day;$('#callback-time').value='11:00';}
$$('input[name="when"]').forEach(input=>input.addEventListener('change',()=>{$('#scheduled-fields').hidden=getInput().when!=='later';$('#schedule-error').textContent='';}));
$('#sample-details').addEventListener('click',()=>{$('#patient-name').value='Aarav Sharma';$('#patient-phone').value='90000 00101';$('#treatment').value='General consultation';$('#clinic').value='Indiranagar';$('#language').value='English';clearErrors();$('#patient-name').focus();notify('Sample details added. Choose a callback time and confirm your preference.');});
$('#request-form').addEventListener('submit',event=>{
  event.preventDefault();if(submitting)return;
  const input=getInput();
  // Validate synchronously so double-clicks cannot enqueue multiple submissions.
  const result=submitRequest(state,input,requestKey);
  if(result.errors){renderErrors(result.errors);return;}
  if(result.error){notify(result.error);return;}
  submitting=true;clearErrors();$('#request-submit').disabled=true;$('#request-submit').textContent='Saving demo request…';
  patientId=result.record.id;selected=patientId;filter='all';clinicFilter='all';query='';scheduleOpen=null;
  $('#clinic-filter').value='all';$('#queue-search').value='';$('#new-lead').hidden=false;
  // The request is already committed to this in-memory demo before confirmation is rendered.
  $('#request-card').hidden=true;$('#request-success').hidden=false;renderPatient();renderWorkspace();
  $('#patient-phone').value='';submitting=false;$('#request-submit').disabled=false;$('#request-submit').textContent='Request my callback';
  $('#request-success').setAttribute('tabindex','-1');$('#request-success').focus({preventScroll:true});notify(result.duplicate?'Your existing request is shown.':'Your demo request is saved. No real call will be placed.');
});

function patientCopy(r){
  if(r.status==='booked')return ['Your appointment is confirmed.','The simulated calendar has returned a booking reference. Your initial consultation details are below.'];
  if(r.status==='scheduled')return ['A callback, on your terms.','Your callback preference is saved. We won’t call before the time you chose.'];
  if(r.status==='stopped')return ['We’ve stopped your callbacks.',r.appointment?'Your confirmed appointment remains booked. Contact preferences and appointment status are separate.':'No more simulated calls will be made for this enquiry.'];
  if(r.status==='resolved')return ['Your enquiry is resolved.','Clinic staff have marked this follow-up complete.'];
  if(r.status==='uncertain')return ['Your appointment needs a check.','We couldn’t confirm the appointment. The clinic will check the existing request before making another booking.'];
  if(ATTENTION.has(r.status))return ['The clinic team will take it from here.','Your request is with the front desk. An attempted transfer isn’t a completed handoff; the follow-up stays visible.'];
  if(['ringing','connected'].includes(r.status))return ['Let’s preview your callback.','This is a simulated conversation. You can stop it or ask the front desk to take over.'];
  return ['You’re on our callback list.','Our AI assistant will help with appointment logistics. Ask for a person at any time. This demo won’t dial your phone.'];
}
function scheduleForm(prefix){return `<form class="inline-schedule" data-schedule-form="${prefix}"><div class="field"><label for="${prefix}-date">Date</label><input id="${prefix}-date" name="date" type="date" min="${state.day}" max="${dayAfter(state.day,30)}" value="${state.day}" required></div><div class="field"><label for="${prefix}-time">Time · IST</label><select id="${prefix}-time" name="time"><option value="11:00">11:00 AM</option><option value="12:00">12:00 PM</option><option value="14:00">2:00 PM</option><option value="16:00">4:00 PM</option><option value="18:00">6:00 PM</option><option value="19:00">7:00 PM</option></select></div><p class="field-error" role="alert"></p><button class="button secondary" type="submit">Save callback preference</button></form>`;}
function renderPatient(){const r=currentPatient();if(!r){$('#request-card').hidden=false;$('#request-success').hidden=true;return;}const [title,copy]=patientCopy(r);const busy=['ringing','connected'].includes(r.status);const canPlay=r.status==='queued';
  $('#request-success').innerHTML=`<div class="success-icon">${icon(r.status==='booked'?'calendar':ATTENTION.has(r.status)?'users':r.status==='stopped'?'shield':'check')}</div>${badge(r)}<h2>${escape(title)}</h2><p class="success-copy">${escape(copy)}</p><span class="request-reference">REQUEST ${escape(r.id)} · FICTIONAL DEMO</span><div class="request-summary"><div class="summary-row"><span>Contact</span><strong>${escape(r.name)} · +91 •••••• ${escape(r.last4)}</strong></div><div class="summary-row"><span>Clinic</span><strong>${escape(r.clinic)}</strong></div><div class="summary-row"><span>Interest</span><strong>${escape(r.service)}</strong></div><div class="summary-row"><span>${r.appointment?'Consultation':'Callback'}</span><strong>${r.appointment?escape(dateLabel(r.appointment.date)+' · '+r.appointment.time):escape(scheduleLabel(r.scheduledAt))}</strong></div>${r.appointment?`<div class="summary-row"><span>Booking reference</span><strong>${escape(r.appointment.reference)}</strong></div>`:''}</div>${busy?`<div class="call-progress"><span class="spinner"></span>${r.status==='ringing'?'Simulated callback is ringing…':'Fictional conversation in progress…'}<small>No phone call or audio recording is taking place.</small></div>`:''}<div class="success-actions">${canPlay?'<button class="button primary full" data-patient-action="play">Play simulated callback</button>':''}<button class="button ${canPlay?'secondary':'primary'} full" data-patient-action="workspace">View clinic workspace</button>${busy?'<button class="button secondary full" data-patient-action="takeover">Ask clinic staff to take over</button>':''}</div>${scheduleOpen==='patient'?scheduleForm('patient'):''}<div class="success-links">${['queued','scheduled'].includes(r.status)?'<button class="text-button" data-patient-action="reschedule">Change callback time</button>':''}${!['stopped','resolved'].includes(r.status)?'<button class="text-button" data-patient-action="stop">Stop callbacks</button>':'<button class="text-button" data-patient-action="new">Try another sample request</button>'}</div>`;
}
$('#request-success').addEventListener('click',event=>{const action=event.target.closest('[data-patient-action]')?.dataset.patientAction;const r=currentPatient();if(!action||!r)return;
  if(action==='play')play(r.id);
  if(action==='workspace'){selected=r.id;filter='all';showView('clinic',{focus:true});}
  if(action==='takeover'){const result=staffAction(state,r.id,'claim');if(result.error)notify(result.error);else{r.reason='The patient requested clinic staff during the simulated callback.';update();notify('The AI simulation stopped. Neha Patel now owns the follow-up.');}}
  if(action==='reschedule'){scheduleOpen=scheduleOpen==='patient'?null:'patient';renderPatient();if(scheduleOpen)$('#patient-date').focus();}
  if(action==='stop')applyAction(r.id,'stop');
  if(action==='new'){patientId=null;requestKey=makeKey();$('#request-form').reset();clearErrors();setScheduleDefaults();$('#scheduled-fields').hidden=true;renderPatient();$('#sample-details').focus();}
});
$('#request-success').addEventListener('submit',event=>{if(!event.target.matches('[data-schedule-form]'))return;event.preventDefault();saveSchedule(event.target,currentPatient().id,'patient');});

function update(){renderPatient();renderWorkspace();}
function delayed(fn,delay){const ticket=setTimeout(()=>{timers.delete(ticket);fn();},delay);timers.add(ticket);}
function play(id){const record=state.entries.find(r=>r.id===id);const result=startCall(record,state.now);if(result.error){notify(result.error);return;}const operation=result.operation;const epoch=generation;const scenario=$('#scenario').value;update();notify('Playing a simulated callback. No real number is dialled.');
  delayed(()=>{if(epoch!==generation)return;if(connectCall(record,operation)){update();$('#live-status').textContent='Simulated conversation connected. The assistant identifies itself as AI.';}},1300);
  delayed(()=>{if(epoch!==generation)return;if(finishCall(state,record,operation,scenario)){update();notify(STATUS[record.status].label+'.');}},3600);
}

function renderMetrics(){const counts=stats(state,clinicFilter);const metrics=[['total','Enquiries','In this fictional session','inbox'],['attention','Needs attention','Staff action required','users'],['booked','Confirmed bookings','Calendar-confirmed examples','calendar'],['scheduled','Scheduled callbacks','Patient’s chosen time','clock']];
  $('#metric-row').innerHTML=metrics.map(([key,label,note,symbol])=>`<div class="metric-card ${key==='attention'?'focus-metric':''}"><div><strong>${counts[key]}</strong><p>${label}</p><small>${note}</small></div><span class="metric-icon">${icon(symbol)}</span></div>`).join('');$('#attention-count').textContent=counts.attention;$('#queue-count').textContent=counts.total;
}
function renderQueue(){const entries=filterEntries(state,{filter,clinic:clinicFilter,query});$$('[data-filter]').forEach(button=>{button.classList.toggle('active',button.dataset.filter===filter);button.setAttribute('aria-pressed',String(button.dataset.filter===filter));});
  if(!entries.some(r=>r.id===selected))selected=entries[0]?.id??null;
  $('#enquiry-list').innerHTML=entries.length?entries.map(r=>`<button class="enquiry-item ${r.id===selected?'selected':''}" data-enquiry="${r.id}" aria-pressed="${r.id===selected}" aria-label="${escape(r.name)}, ${escape(STATUS[r.status].label)}">${avatar(r)}<span class="enquiry-content"><span class="enquiry-topline"><strong>${escape(r.name)}</strong><time>${escape(r.age)}</time></span><span class="enquiry-service">${escape(r.service)} · ${escape(r.clinic)}</span><span class="enquiry-bottomline">${badge(r)}<span class="enquiry-next">${escape(r.owner||STATUS[r.status].next)}</span></span></span></button>`).join(''):`<div class="empty-state">${icon('inbox')}<h3>${query?'No matching enquiries':filter==='attention'?'Everything here is taken care of':'No enquiries here yet'}</h3><p>${query?'Try another name, service or reference.':filter==='attention'?'Switch to All enquiries to see the rest of this session.':'Change the filters or create a sample patient request.'}</p></div>`;
}
function getCallout(r){
  if(r.status==='followup'||r.status==='human')return {tone:'',title:r.owner?'Follow-up owned by '+r.owner:'A person is needed here',body:r.reason||'The clinic team owns the next step. The AI will not continue this enquiry.',meta:r.owner?`Owner: ${r.owner} · Due ${r.due||'10:45 AM IST'}`:`Unassigned · Follow-up due ${r.due||'10:40 AM IST'}`,symbol:'users'};
  if(r.status==='uncertain')return {tone:'',title:'Check the existing booking before retrying',body:r.reason,meta:`Request key: ${r.bookingKey} · ${r.owner||'Unassigned'}`,symbol:'alert'};
  if(r.status==='booked')return {tone:'green',title:'Confirmed, with a booking reference',body:'The simulated calendar has confirmed this initial consultation. No staff task is required.',meta:'Confirmation messages are not sent in this prototype.',symbol:'check'};
  if(r.status==='scheduled')return {tone:'blue',title:'The patient chose when to talk',body:`Callback arranged for ${scheduleLabel(r.scheduledAt)}. No call will be made before that time.`,meta:`Next owner: ${r.owner||'AI assistant'} · No appointment booked`,symbol:'clock'};
  if(r.status==='queued')return {tone:'blue',title:'Ready for a timely callback',body:'The callback request and contact preference are recorded. Play the simulated callback to see the selected outcome.',meta:'Demo controls let you choose the callback outcome.',symbol:'phone'};
  if(['ringing','connected'].includes(r.status))return {tone:'blue',title:r.status==='ringing'?'Simulated callback is ringing':'Fictional conversation in progress',body:'The assistant identifies itself as AI. Staff takeover or a stop request immediately cancels incompatible simulated work.',meta:'No real phone call or recording is taking place.',symbol:'phone'};
  if(r.status==='stopped')return {tone:'gray',title:'No further contact',body:r.appointment?'All future callbacks are stopped. The previously confirmed appointment remains booked.':'All pending callbacks are stopped. This enquiry cannot be restarted without a new request.',meta:'No automated retries scheduled',symbol:'shield'};
  return {tone:'gray',title:'Follow-up complete',body:'Clinic staff have marked the enquiry resolved. No more automated work is scheduled.',meta:`Resolved by ${r.owner||'clinic staff'}`,symbol:'check'};
}
function actionButtons(r){const actions=[];if(r.status==='queued')actions.push(['play','Play simulated callback','primary']);if((ATTENTION.has(r.status)||['queued','scheduled','ringing','connected'].includes(r.status))&&!r.owner)actions.push(['claim','Take ownership','primary']);if(r.status==='uncertain')actions.push(['reconcile','Check simulated calendar','secondary']);if(r.owner==='Neha Patel'&&['human','followup'].includes(r.status))actions.push(['resolve','Mark follow-up resolved','primary']);if(['human','followup','queued','scheduled'].includes(r.status))actions.push(['schedule','Arrange callback','secondary']);return actions.map(([action,label,style])=>`<button class="button ${style}" data-action="${action}" data-record="${r.id}">${label}</button>`).join('');}
function renderDetail(){const r=state.entries.find(e=>e.id===selected);if(!r){$('#enquiry-detail').innerHTML=`<div class="empty-state">${icon('users')}<h3>A clear view of every conversation.</h3><p>Select an enquiry to see its outcome and next step.</p></div>`;return;}
  const callout=getCallout(r);
  $('#enquiry-detail').innerHTML=`<div class="detail-header">${avatar(r)}<div class="detail-title"><h2>${escape(r.name)}</h2><p>${escape(r.id)} · +91 •••••• ${escape(r.last4)}</p></div>${badge(r)}</div><div class="detail-facts"><div><span>Interested in</span><strong>${escape(r.service)}</strong></div><div><span>Preferred clinic</span><strong>${escape(r.clinic)}</strong></div><div><span>Language</span><strong>${escape(r.language)}</strong></div></div><div class="detail-body"><div class="action-callout ${callout.tone}"><div class="callout-top">${icon(callout.symbol)}<strong>${escape(callout.title)}</strong></div><p>${escape(callout.body)}</p><div class="callout-meta">${icon('clock')}<span>${escape(callout.meta)}</span></div><div class="callout-actions">${actionButtons(r)}</div>${scheduleOpen===r.id?scheduleForm('staff'):''}</div><section class="detail-section"><h3>Conversation summary <span>Fictional example</span></h3><p>${escape(r.summary)}</p><div class="summary-chips"><span class="summary-chip">${r.consent?'Callback requested':'Contact stopped'}</span><span class="summary-chip">${r.attempts} simulated ${r.attempts===1?'attempt':'attempts'}</span><span class="summary-chip">Website enquiry</span></div></section>${r.appointment?`<section class="detail-section"><h3>Confirmed consultation</h3><div class="appointment-card"><span>${icon('calendar')}</span><div><strong>${escape(dateLabel(r.appointment.date,{weekday:'short'}))} · ${escape(r.appointment.time)}</strong><small>${escape(r.appointment.clinic)} · ${escape(r.appointment.type)}</small><small>Reference ${escape(r.appointment.reference)}</small></div></div></section>`:''}<section class="detail-section"><h3>Activity <span>Demo clock · IST</span></h3><ol class="timeline">${r.events.map(ev=>`<li><span>${escape(ev.label)}</span><time>${escape(ev.time)}</time></li>`).join('')}</ol></section></div><div class="detail-bottom"><span>${icon('lock')}${r.consent?'Contact preference recorded at intake':'Contact stopped; retries suppressed'}</span>${!['stopped','resolved'].includes(r.status)?`<button class="text-button" data-action="stop" data-record="${r.id}">Stop callbacks</button>`:''}</div>`;
}
function renderWorkspace(){renderMetrics();renderQueue();renderDetail();}
$$('[data-filter]').forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.filter;scheduleOpen=null;renderWorkspace();}));
$('#clinic-filter').addEventListener('change',event=>{clinicFilter=event.target.value;scheduleOpen=null;renderWorkspace();});
$('#queue-search').addEventListener('input',event=>{query=event.target.value;scheduleOpen=null;renderQueue();renderDetail();});
$('#enquiry-list').addEventListener('click',event=>{const button=event.target.closest('[data-enquiry]');if(!button)return;selected=button.dataset.enquiry;scheduleOpen=null;renderWorkspace();$(`[data-enquiry="${selected}"]`)?.focus({preventScroll:true});if(matchMedia('(max-width: 800px)').matches)$('#enquiry-detail').scrollIntoView({behavior:'smooth',block:'start'});});
function applyAction(id,action,payload={}){const result=staffAction(state,id,action,payload);if(result.error){notify(result.error);return false;}scheduleOpen=null;update();const focusTarget=view==='clinic'?$('#enquiry-detail'):$('#request-success');focusTarget.setAttribute('tabindex','-1');focusTarget.focus({preventScroll:true});const messages={claim:'Neha Patel owns the next step. Incompatible AI work has stopped.',stop:'Contact stopped. All pending simulated callbacks are cancelled.',resolve:'Staff follow-up marked resolved.',reconcile:'Original booking found in the simulated calendar. No duplicate was created.',schedule:'Callback preference saved. Any earlier pending callback is cancelled.'};notify(messages[action]||'Enquiry updated.');return true;}
$('#enquiry-detail').addEventListener('click',event=>{const button=event.target.closest('[data-action]');if(!button)return;const {action,record}=button.dataset;if(action==='play'){play(record);return;}if(action==='schedule'){scheduleOpen=scheduleOpen===record?null:record;renderDetail();if(scheduleOpen)$('#staff-date').focus();return;}applyAction(record,action);});
function saveSchedule(form,id,actor){const values=new FormData(form);const payload={date:values.get('date'),time:values.get('time'),actor};const error=validateSchedule(payload.date,payload.time,state.now);if(error){form.querySelector('.field-error').textContent=error;return;}const result=staffAction(state,id,'schedule',payload);if(result.error){form.querySelector('.field-error').textContent=result.error;return;}scheduleOpen=null;update();notify('Callback time updated. The earlier callback is cancelled.');}
$('#enquiry-detail').addEventListener('submit',event=>{if(!event.target.matches('[data-schedule-form]'))return;event.preventDefault();saveSchedule(event.target,selected,'staff');});
$('#reset-demo').addEventListener('click',()=>{generation+=1;timers.forEach(clearTimeout);timers.clear();state=createState();selected='HS-1048';patientId=null;requestKey=makeKey();filter='attention';clinicFilter='all';query='';scheduleOpen=null;submitting=false;$('#request-form').reset();$('#scheduled-fields').hidden=true;$('#clinic-filter').value='all';$('#queue-search').value='';$('#scenario').value='booking';$('#new-lead').hidden=true;$('#demo-controls').open=false;clearErrors();setScheduleDefaults();update();notify('Demo reset. All pending simulations were cancelled.');});

$('#workspace-date').textContent=dateLabel(state.day,{weekday:'short',year:'numeric'});
setScheduleDefaults();renderWorkspace();showView(view,{hash:false});
