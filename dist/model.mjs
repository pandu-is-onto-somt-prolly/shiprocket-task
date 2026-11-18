export const CLINICS = ['Indiranagar', 'Koramangala', 'Whitefield'];
export const SERVICES = ['General consultation', 'Braces & aligners', 'Teeth whitening', 'Dental implants'];
export const LANGUAGES = ['English', 'Hindi', 'Kannada'];
export const SCENARIOS = ['booking', 'callback', 'handoff', 'uncertain', 'language'];
export const ATTENTION = new Set(['followup', 'uncertain', 'human']);
export const STATUS = {
  queued: {label:'Callback queued',color:'blue',next:'AI assistant'},
  scheduled: {label:'Callback scheduled',color:'blue',next:'Scheduled callback'},
  ringing: {label:'Simulated call ringing',color:'blue',next:'AI assistant'},
  connected: {label:'Conversation in progress',color:'blue',next:'AI assistant'},
  booked: {label:'Appointment confirmed',color:'green',next:'No action needed'},
  followup: {label:'Staff follow-up needed',color:'amber',next:'Needs an owner'},
  uncertain: {label:'Booking not confirmed',color:'amber',next:'Check calendar'},
  human: {label:'With front desk',color:'amber',next:'Staff owns next step'},
  stopped: {label:'Contact stopped',color:'gray',next:'No further calls'},
  resolved: {label:'Enquiry resolved',color:'gray',next:'No action needed'},
};
export function demoDate() {
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const value = k => parts.find(p=>p.type===k).value;
  return `${value('year')}-${value('month')}-${value('day')}`;
}
export function clock(day) { return `${day}T10:30:00+05:30`; }
export function dayAfter(day, amount=1) {return new Date(Date.parse(`${day}T12:00:00Z`)+amount*86400000).toISOString().slice(0,10);}
export function normalizePhone(value) {
  let s = String(value ?? '').replace(/[\s()-]/g,'');
  if(s.startsWith('+91')) s=s.slice(3);
  if(/^91[6-9]\d{9}$/.test(s)) s=s.slice(2);
  return /^[6-9]\d{9}$/.test(s)?s:null;
}
export function validateSchedule(day,time,now) {
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day||'') || !/^\d{2}:\d{2}$/.test(time||'')) return 'Choose a callback date and time.';
  const parsed=Date.parse(`${day}T${time}:00+05:30`);
  if(!Number.isFinite(parsed) || new Date(parsed+19800000).toISOString().slice(0,10)!==day) return 'Choose a valid callback date.';
  const [hour,minute]=time.split(':').map(Number);
  if(hour<9 || hour>=20 || minute>59) return 'Choose a time between 9:00 AM and 7:59 PM IST.';
  if(parsed<=Date.parse(now)) return 'Choose a callback time after 10:30 AM IST on the demo day.';
  if(parsed-Date.parse(now)>30*86400000) return 'Please choose a callback within the next 30 days.';
  return null;
}
export function validateRequest(input,now) {
  const errors={};
  if(!String(input.name||'').trim() || String(input.name).trim().length>70) errors.name='Please enter a name of 1–70 characters.';
  if(!normalizePhone(input.phone)) errors.phone='Enter a valid 10-digit Indian mobile number.';
  if(!CLINICS.includes(input.clinic)) errors.clinic='Choose one of the demo clinics.';
  if(!SERVICES.includes(input.service)) errors.service='Choose a listed service.';
  if(!LANGUAGES.includes(input.language)) errors.language='Choose a supported demo language.';
  if(!input.consent) errors.consent='Please confirm that you would like this AI callback.';
  if(!['soon','later'].includes(input.when)) errors.schedule='Choose when to receive your callback.';
  if(input.when==='later') {const error=validateSchedule(input.date,input.time,now);if(error)errors.schedule=error;}
  return errors;
}
function event(record,label,time='10:30 AM') {record.events.unshift({label,time});}
function appointment(state,record,reference) {
  const date=dayAfter(state.day);
  const slots=['11:30 AM IST','12:00 PM IST','12:30 PM IST','2:00 PM IST','2:30 PM IST','3:00 PM IST','3:30 PM IST','4:00 PM IST','4:30 PM IST','5:00 PM IST'];
  const occupied=new Set(state.entries.filter(r=>r.id!==record.id&&r.appointment?.state==='confirmed'&&r.appointment.clinic===record.clinic&&r.appointment.date===date).map(r=>r.appointment.time));
  const time=slots.find(slot=>!occupied.has(slot));
  return time?{reference,date,time,type:'Initial consultation',clinic:record.clinic,state:'confirmed'}:null;
}
export function createState(day=demoDate()) {
  const entries=[
    {id:'HS-1048',name:'Priya Mehta',initials:'PM',color:'lilac',last4:'0128',clinic:'Indiranagar',service:'Braces & aligners',language:'English',status:'followup',reason:'The patient asked for clinic staff. The transfer rang unanswered.',summary:'Interested in an initial braces consultation. Prefers a weekend visit and asked to speak with clinic staff before booking.',age:'8 min ago',owner:null,due:'10:40 AM IST',events:[{label:'Staff transfer unanswered; follow-up task created',time:'10:24 AM'},{label:'Requested to speak with the clinic',time:'10:23 AM'},{label:'AI callback connected',time:'10:22 AM'},{label:'Callback requested; contact permission recorded',time:'10:22 AM'}]},
    {id:'HS-1047',name:'Rohan Iyer',initials:'RI',color:'blue',last4:'0419',clinic:'Koramangala',service:'Teeth whitening',language:'English',status:'booked',summary:'Requested a consultation about whitening. The clinic, appointment date and time were read back and accepted.',age:'14 min ago',events:[{label:'Appointment confirmed in the simulated calendar',time:'10:19 AM'},{label:'Appointment details read back and accepted',time:'10:18 AM'},{label:'AI callback connected',time:'10:17 AM'},{label:'Callback requested; contact permission recorded',time:'10:16 AM'}]},
    {id:'HS-1046',name:'Aditi Rao',initials:'AR',color:'green',last4:'0786',clinic:'Whitefield',service:'Dental implants',language:'Hindi',status:'uncertain',reason:'The calendar did not return a confirmation. Check the existing request before trying again.',summary:'Requested an initial consultation about implants. The appointment request timed out, so no appointment has been promised. Treatment suitability remains for the dentist.',bookingKey:'DEMO-REQ-1046',age:'20 min ago',due:'10:40 AM IST',events:[{label:'Calendar response uncertain; reconciliation needed',time:'10:14 AM'},{label:'Consultation preference confirmed',time:'10:13 AM'},{label:'AI callback connected in Hindi',time:'10:12 AM'},{label:'Callback requested; contact permission recorded',time:'10:10 AM'}]},
    {id:'HS-1045',name:'Vikram Shah',initials:'VS',color:'blue',last4:'0527',clinic:'Indiranagar',service:'General consultation',language:'English',status:'scheduled',scheduledAt:`${day}T12:00:00+05:30`,summary:'The patient was busy and requested a callback at 12:00 PM IST. No appointment has been booked.',age:'27 min ago',events:[{label:'Callback scheduled for 12:00 PM IST',time:'10:06 AM'},{label:'Patient asked to talk later',time:'10:05 AM'},{label:'AI callback connected',time:'10:04 AM'},{label:'Callback requested; contact permission recorded',time:'10:03 AM'}]},
    {id:'HS-1044',name:'Meera Nair',initials:'MN',color:'lilac',last4:'0638',clinic:'Koramangala',service:'Braces & aligners',language:'Kannada',status:'human',owner:'Neha Patel',reason:'The patient has questions about an existing treatment plan. Front desk owns the follow-up.',summary:'Asked about an existing braces treatment plan. The assistant did not give clinical advice and routed the question to the clinic.',age:'35 min ago',due:'10:45 AM IST',events:[{label:'Neha Patel claimed the follow-up',time:'10:00 AM'},{label:'Clinical question routed to clinic staff',time:'9:58 AM'},{label:'AI callback connected',time:'9:56 AM'},{label:'Callback requested; contact permission recorded',time:'9:55 AM'}]},
    {id:'HS-1043',name:'Kabir Sen',initials:'KS',color:'green',last4:'0935',clinic:'Indiranagar',service:'Teeth whitening',language:'English',status:'stopped',consent:false,summary:'The patient no longer wants a callback. All pending simulated outreach has been stopped.',age:'42 min ago',events:[{label:'Contact stopped; pending callbacks cancelled',time:'9:52 AM'},{label:'Patient requested no further calls',time:'9:51 AM'},{label:'Callback requested',time:'9:48 AM'}]},
  ].map(r=>({consent:true,owner:null,operation:0,attempts:1,source:'Website callback request',synthetic:true,...r}));
  const state={version:1,day,now:clock(day),entries,nextId:1049,requestKeys:{},demoPatientId:null};
  entries[1].appointment=appointment(state,entries[1],'DEMO-2047');
  return state;
}
export function submitRequest(state,input,key) {
  if(typeof key!=='string'||!key) return {error:'The request reference is missing. Please retry.'};
  const existing=state.requestKeys[key];
  if(existing) return {record:state.entries.find(x=>x.id===existing),duplicate:true};
  const errors=validateRequest(input,state.now);
  if(Object.keys(errors).length) return {errors};
  const phone=normalizePhone(input.phone);
  // Only use the normalized number to validate and mask it. Never store a raw phone number.
  const id=`HS-${state.nextId++}`;
  const name=input.name.trim();
  const record={id,name,initials:name.split(/\s+/).slice(0,2).map(x=>Array.from(x)[0]).join('').toUpperCase(),color:'green',last4:phone.slice(-4),clinic:input.clinic,service:input.service,language:input.language,status:input.when==='later'?'scheduled':'queued',scheduledAt:input.when==='later'?`${input.date}T${input.time}:00+05:30`:null,consent:true,owner:null,operation:0,attempts:0,age:'Just now',summary:input.when==='later'?'A callback has been arranged at the requested time. No call or booking has taken place.':'A new callback request is waiting for the AI assistant. No call or booking has taken place.',source:'Website callback request',synthetic:true,events:[{label:input.when==='later'?'Callback scheduled; contact permission recorded':'Callback requested; contact permission recorded',time:'10:30 AM'}]};
  state.entries.unshift(record);state.requestKeys[key]=id;state.demoPatientId=id;
  return {record};
}
export function startCall(record,now) {
  if(!record||!record.consent||!['queued','scheduled'].includes(record.status))return {error:'This enquiry is not available for an AI callback.'};
  if(record.scheduledAt&&Date.parse(record.scheduledAt)>Date.parse(now))return {error:'This callback is scheduled for later. It will not be dialled early.'};
  record.operation+=1;record.status='ringing';record.attempts+=1;record.owner=null;
  event(record,'Simulated AI callback initiated');return {operation:record.operation};
}
export function connectCall(record,operation) {
  if(!record||record.operation!==operation||!record.consent||record.status!=='ringing')return false;
  record.status='connected';event(record,'Simulated call connected; AI identity disclosed');return true;
}
export function finishCall(state,record,operation,scenario) {
  if(!record||record.operation!==operation||!record.consent||record.status!=='connected'||!SCENARIOS.includes(scenario))return false;
  if(scenario==='booking') {
    const booking=appointment(state,record,`DEMO-B${record.id.slice(3)}`);
    if(!booking){record.status='followup';record.reason='No consultation slots remain in the simulated calendar. Staff should offer another date.';record.summary='The patient requested a consultation, but no slot could be confirmed. No appointment has been promised.';record.due='10:40 AM IST';event(record,'No available slot; staff follow-up created');return true;}
    record.status='booked';record.appointment=booking;record.summary='The patient chose an initial consultation. Clinic, date and time were confirmed in this fictional conversation. The simulated calendar returned a booking reference.';event(record,'Appointment confirmed in the simulated calendar');
  } else if(scenario==='callback') {
    record.status='scheduled';record.scheduledAt=`${state.day}T16:00:00+05:30`;record.summary='The patient asked to talk at 4:00 PM IST. The preference was confirmed and no appointment was booked.';event(record,'Patient requested a callback at 4:00 PM IST');
  } else if(scenario==='uncertain') {
    record.status='uncertain';record.bookingKey=`DEMO-REQ-${record.id.slice(3)}`;record.reason='The calendar did not return a confirmation. Check the existing request before trying again.';record.summary='The patient selected a consultation time, but the calendar response was uncertain. No appointment has been promised.';record.due='10:40 AM IST';event(record,'Calendar response uncertain; reconciliation task created');
  } else {
    record.status='followup';record.due='10:40 AM IST';record.reason=scenario==='language'?'The patient requested a language outside this demo’s supported set. Arrange a staff callback.':'The patient asked for clinic staff. The transfer rang unanswered.';record.summary=scenario==='language'?'The assistant could not continue confidently in the requested language. It did not infer patient details or attempt to book.':'The patient asked for a person. The simulated transfer was unanswered, so staff follow-up is required. No appointment has been booked.';event(record,scenario==='language'?'Unsupported language; staff callback task created':'Staff transfer unanswered; follow-up task created');
  }
  return true;
}
export function staffAction(state,id,action,payload={}) {
  const record=state.entries.find(r=>r.id===id);
  if(!record)return {error:'This enquiry is no longer available.'};
  if(action==='stop') {
    if(['stopped','resolved'].includes(record.status))return {error:'There is no pending contact to stop.'};
    record.operation+=1;record.consent=false;record.status='stopped';record.scheduledAt=null;record.owner=null;event(record,'Contact stopped; pending simulated callbacks cancelled');return {record};
  }
  if(!record.consent||record.status==='stopped')return {error:'Contact has stopped. No new callback can be scheduled.'};
  if(action==='claim') {
    if(!ATTENTION.has(record.status)&&!['ringing','connected','queued','scheduled'].includes(record.status))return {error:'This enquiry does not need staff takeover.'};
    if(record.owner)return {error:`This enquiry is already owned by ${record.owner}.`};
    record.operation+=1;record.owner='Neha Patel';if(record.status!=='uncertain')record.status='human';event(record,'Neha Patel took ownership; incompatible AI work stopped');return {record};
  }
  if(action==='resolve') {
    if(record.owner!=='Neha Patel'||!ATTENTION.has(record.status))return {error:'Claim this follow-up before resolving it.'};
    if(record.status==='uncertain')return {error:'Reconcile the uncertain booking before resolving this task.'};
    record.operation+=1;record.status='resolved';event(record,'Staff follow-up marked resolved by Neha Patel');return {record};
  }
  if(action==='schedule') {
    if(record.status==='booked')return {error:'This patient already has an appointment. Avoid a duplicate callback.'};
    if(record.status==='uncertain')return {error:'Reconcile the uncertain booking before scheduling more contact.'};
    if(record.status==='resolved')return {error:'This enquiry is resolved.'};
    const error=validateSchedule(payload.date,payload.time,state.now);if(error)return {error};
    record.operation+=1;record.status='scheduled';record.scheduledAt=`${payload.date}T${payload.time}:00+05:30`;record.owner=payload.actor==='patient'?null:'Neha Patel';event(record,payload.actor==='patient'?'Patient changed their callback preference; old callback cancelled':'Neha Patel arranged a callback at the confirmed preference');return {record};
  }
  if(action==='reconcile') {
    if(record.status!=='uncertain')return {error:'There is no uncertain booking to reconcile.'};
    // Simulate looking up the existing request, not submitting another booking.
    const booking=appointment(state,record,`DEMO-B${record.id.slice(3)}`);if(!booking)return {error:'No simulated booking can be confirmed. Keep this reconciliation task open for staff.'};
    record.appointment=booking;record.status='booked';record.owner='Neha Patel';record.operation+=1;record.summary+=' The simulated lookup found the original booking; no second appointment was created.';event(record,`Existing request ${record.bookingKey} reconciled; original booking found`);return {record};
  }
  return {error:'This action is not supported.'};
}
export function filterEntries(state,{filter='all',clinic='all',query=''}={}) {
  const search=query.trim().toLocaleLowerCase();
  return state.entries.filter(r=>(clinic==='all'||r.clinic===clinic)&&(filter==='all'||(filter==='attention'&&ATTENTION.has(r.status))||(filter==='booked'&&r.appointment?.state==='confirmed'))&&(!search||`${r.name} ${r.id} ${r.service} ${r.clinic}`.toLocaleLowerCase().includes(search)));
}
export function stats(state,clinic='all') {
  const records=state.entries.filter(r=>clinic==='all'||r.clinic===clinic);
  return {total:records.length,attention:records.filter(r=>ATTENTION.has(r.status)).length,booked:records.filter(r=>r.appointment?.state==='confirmed').length,scheduled:records.filter(r=>r.status==='scheduled').length};
}
