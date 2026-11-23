// State-machine tests, not a browser or a substitute for the live UI rehearsal.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function check(path,enabled=true){
 let preference=new Map([['sb_token','unchanged-session']]),listeners={},timers=[],nodes=new Map(),redirects=[];
 const location={pathname:path,search:'?qa=pilot',hash:'#section',origin:'https://example.test',replace:v=>redirects.push(v),assign:v=>redirects.push(v)};
 const document={hidden:false,head:{append(){}},getElementById:id=>nodes.get(id),addEventListener:(name,fn)=>listeners[name]=fn,body:{append:n=>nodes.set(n.id,n)},createElement:tag=>({tag,style:{},children:[],append(...args){this.children.push(...args)},setAttribute(){},remove(){nodes.delete(this.id)}})};
 const context={window:{},document,location,URL,AbortSignal,localStorage:{getItem:k=>preference.get(k),setItem:(k,v)=>preference.set(k,v)},setInterval:fn=>timers.push(fn),fetch:async()=>({ok:true,json:async()=>({enabled,user_id:'owner'})})};
 vm.createContext(context);vm.runInContext(fs.readFileSync('ui/cecil-rollout.js','utf8'),context);
 await context.window.bkCecilRollout({api:'https://staging.test',token:'private-test',userId:'owner'});
 return{preference,listeners,timers,nodes,redirects,revoke(){enabled=false}};
}
(async()=>{
 let s=await check('/contactos.html');let bar=s.nodes.get('cecil-rollout-controls');assert.ok(bar);let button=bar.children.find(c=>c.tag==='button');assert.equal(button.textContent,'Probar el diseño Cecil');button.onclick();assert.equal(s.redirects.at(-1),'/cecil/contactos.html?qa=pilot#section');assert.equal(s.preference.get('sb_token'),'unchanged-session');
 s=await check('/cecil/contactos.html');bar=s.nodes.get('cecil-rollout-controls');button=bar.children.find(c=>c.tag==='button');assert.equal(button.textContent,'Volver a Broquer');button.onclick();assert.equal(s.redirects.at(-1),'/contactos.html?qa=pilot#section');assert.equal(s.preference.get('sb_token'),'unchanged-session');
 s=await check('/cecil/contratos.html');s.revoke();await s.timers[0]();assert.equal(s.redirects.at(-1),'/contratos.html?qa=pilot#section');assert.equal(s.preference.get('sb_token'),'unchanged-session');
 s=await check('/cecil/contactos.html',false);assert.equal(s.nodes.has('cecil-rollout-controls'),false);assert.equal(s.redirects.at(-1),'/contactos.html?qa=pilot#section');
 console.log('Pilot state machine: opt-in, return, revocation and session preservation passed (unit only).');
})();
