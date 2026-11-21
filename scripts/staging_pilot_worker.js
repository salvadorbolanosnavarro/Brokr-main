// Staging-only authentication and error probe. No service-role key or variables.
const DB = 'https://tymhlvawnqadqgwnpruk.supabase.co';
const KEY = 'sb_publishable_oXqQTLbZh012xaO_6IRUcA_e6-C0fwi';
const INGEST = 'https://o4511509854945280.ingest.us.sentry.io/api/4511509862744064/envelope/';
const DSN = 'https://266e3bda223d2a0a211074bde709f4e8@o4511509854945280.ingest.us.sentry.io/4511509862744064';
const response = (data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json','Cache-Control':'private, no-store','Vary':'Authorization'}});
export async function pilotRequest(request, fetcher=fetch) {
 const path=new URL(request.url).pathname;
 if (!['/ui/cecil','/__staging/error-probe'].includes(path)) return null;
 const expected=path==='/ui/cecil'?'GET':'POST';
 if(request.method!==expected)return response({detail:'Method not allowed'},405);
 const authorization=request.headers.get('Authorization')||'';
 if(!/^Bearer [A-Za-z0-9._-]+$/.test(authorization))return response({detail:'Authentication required'},401);
 const headers={apikey:KEY,Authorization:authorization};
 try {
  const auth=await fetcher(DB+'/auth/v1/user',{headers,signal:AbortSignal.timeout(6000)});
  if(!auth.ok)return response({detail:'Invalid staging session'},401);
  const user=await auth.json();
  if(!/^[0-9a-f-]{36}$/.test(user.id||''))return response({detail:'Invalid identity'},401);
  const flag=await fetcher(DB+'/rest/v1/cecil_staging_pilot?select=user_id,enabled&user_id=eq.'+user.id,{headers,signal:AbortSignal.timeout(6000)});
  if(!flag.ok)return response({enabled:false,user_id:user.id},503);
  const rows=await flag.json();
  const enabled=rows.length===1&&rows[0].user_id===user.id&&rows[0].enabled===true;
  if(path==='/ui/cecil'){const r=response({enabled,user_id:user.id});r.headers.set('Set-Cookie','cecil_staging_session='+authorization.slice(7)+'; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600');return r;}
  if(!enabled)return response({detail:'Staging pilot access required'},403);
  // Never accept caller messages, stack traces, cookies, PII or credentials.
  if(Number(request.headers.get('Content-Length')||0)>1024)return response({detail:'Payload too large'},413);
  const raw=await request.text();if(raw.length>1024)return response({detail:'Payload too large'},413);
  const input=(()=>{try{return JSON.parse(raw)}catch(_){return {}}})();
  if(!['controlled-error-v1','runtime-error-v1'].includes(input.probe)||Object.keys(input).length!==1)return response({detail:'Expected controlled probe'},422);
  const eventId=crypto.randomUUID();
  const message=input.probe==='controlled-error-v1'?'CECIL_STAGING_CONTROLLED_ERROR':'CECIL_STAGING_RUNTIME_ERROR';
  const event={event_id:eventId.replaceAll('-',''),timestamp:new Date().toISOString(),platform:'javascript',level:'error',environment:'staging',release:'cecil-staging-pilot-20261121',message,exception:{values:[{type:'Error',value:message,mechanism:{type:'handled',handled:true}}]},tags:{qa:input.probe,source:'staging-preview'}};
  const envelope=JSON.stringify({event_id:event.event_id,dsn:DSN,sent_at:new Date().toISOString()})+'\n'+JSON.stringify({type:'event'})+'\n'+JSON.stringify(event);
  const sentry=await fetcher(INGEST,{method:'POST',headers:{'Content-Type':'application/x-sentry-envelope'},body:envelope,signal:AbortSignal.timeout(10000)});
  const accepted=sentry.ok;
  const receipt=await fetcher(DB+'/rest/v1/cecil_staging_error_receipts',{method:'POST',headers:{...headers,'Content-Type':'application/json',Prefer:'return=minimal'},body:JSON.stringify({event_id:eventId,user_id:user.id,sentry_accepted:accepted}),signal:AbortSignal.timeout(6000)});
  return response({event_id:eventId,sentry_status:sentry.status,sentry_accepted:accepted,receipt_saved:receipt.ok,environment:'staging'},accepted&&receipt.ok?200:502);
 } catch (_) {return response({detail:'Staging pilot unavailable',enabled:false},503);}
}
