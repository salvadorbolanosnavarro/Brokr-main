// State-machine tests, not a browser or a substitute for the live UI rehearsal.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const label=n=>typeof n==='string'?n:(n.textContent||'')+(n.children||[]).map(label).join('');
function find(node,text){if(!node||typeof node!=='object')return null;if(node.tag==='button'&&label(node)===text)return node;for(const c of node.children||[]){const f=find(c,text);if(f)return f;}return null;}
async function check(path,{enabled=true,user='owner',reply}={}){
 let preference=new Map([['sb_token','unchanged-session']]),listeners={},timers=[],nodes=new Map(),redirects=[],calls=[];
 const location={pathname:path,search:'?qa=pilot',hash:'#section',origin:'https://example.test',replace:v=>redirects.push(v),assign:v=>redirects.push(v)};
 const el=tag=>({tag,style:{},children:[],textContent:'',append(...args){this.children.push(...args)},setAttribute(){},remove(){nodes.delete(this.id)},contains(){return false}});
 const document={hidden:false,head:{append(){}},getElementById:id=>nodes.get(id),addEventListener:(name,fn)=>(listeners[name]=listeners[name]||[]).push(fn),body:{append:n=>nodes.set(n.id,n)},createElement:el};
 const respond=reply||((tok)=>({ok:true,status:200,json:async()=>({enabled,user_id:user})}));
 const context={window:{},document,location,URL,URLSearchParams,AbortSignal,localStorage:{getItem:k=>preference.get(k),setItem:(k,v)=>preference.set(k,v)},setInterval:fn=>timers.push(fn),setTimeout,clearTimeout,
  fetch:async(_u,o)=>{const tok=o.headers.Authorization.slice(7);calls.push(tok);return respond(tok);}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('ui/cecil-rollout.js','utf8'),context);
 let current='session-1';
 await context.window.bkCecilRollout({api:'https://staging.test',getToken:()=>current,refreshToken:async()=>(current='session-2'),userId:'owner'});
 return{preference,listeners,timers,nodes,redirects,calls,revoke(){enabled=false},other(){user='intruder'}};
}
(async()=>{
 let s=await check('/contactos.html');let bar=s.nodes.get('cecil-rollout-controls');assert.ok(bar);let button=find(bar,'Probar el diseño Cecil');button.onclick();assert.equal(s.redirects.at(-1),'/cecil/contactos.html?qa=pilot#section');assert.equal(s.preference.get('sb_token'),'unchanged-session');
 s=await check('/cecil/contactos.html');bar=s.nodes.get('cecil-rollout-controls');assert.ok(find(bar,'Cecil · piloto'));button=find(bar,'Volver a Broquer');button.onclick();assert.equal(s.redirects.at(-1),'/contactos.html?qa=pilot#section');assert.equal(s.preference.get('sb_token'),'unchanged-session');
 s=await check('/cecil/contratos.html');s.revoke();await s.timers[0]();assert.equal(s.redirects.at(-1),'/contratos.html?qa=pilot#section');assert.equal(s.preference.get('sb_token'),'unchanged-session');
 s=await check('/cecil/contratos.html');s.other();await s.timers[0]();assert.equal(s.redirects.at(-1),'/contratos.html?qa=pilot#section');
 s=await check('/cecil/contactos.html',{enabled:false});assert.equal(s.nodes.has('cecil-rollout-controls'),false);assert.equal(s.redirects.at(-1),'/contactos.html?qa=pilot#section');
 // Expired token: 401 for the old token, refresh, retry with the new one, stay.
 let expired=false;
 s=await check('/cecil/contratos.html',{reply:tok=>expired&&tok==='session-1'?{ok:false,status:401,json:async()=>({})}:{ok:true,status:200,json:async()=>({enabled:true,user_id:'owner'})}});
 expired=true;s.calls.length=0;await s.timers[0]();assert.deepEqual(s.calls,['session-1','session-2']);assert.equal(s.redirects.length,0);
 s.calls.length=0;await s.timers[0]();assert.deepEqual(s.calls,['session-2'],'reads the current token every time');
 // Network failure and server errors: stay.
 let mode='ok';
 s=await check('/cecil/contratos.html',{reply:()=>{if(mode==='down')throw new TypeError('Failed to fetch');if(mode==='5xx')return{ok:false,status:503,json:async()=>({})};return{ok:true,status:200,json:async()=>({enabled:true,user_id:'owner'})};}});
 mode='down';await s.timers[0]();mode='5xx';await s.timers[0]();assert.equal(s.redirects.length,0);
 s=await check('/cecil/contratos.html',{reply:()=>{throw new TypeError('offline');}});assert.equal(s.redirects.length,0);assert.ok(s.nodes.has('cecil-rollout-controls'));
 console.log('Pilot state machine: opt-in, return, revocation, expired token refresh, network failures and session preservation passed (unit only).');
})().catch(e=>{console.error(e);process.exitCode=1;});
