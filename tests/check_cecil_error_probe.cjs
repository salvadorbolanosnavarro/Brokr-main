const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function check(code,lazy=false){
 let callback,processor,captured;const children=[];
 const Sentry={getClient:()=>({on:(_name,fn)=>{callback=fn;return()=>{};}}),withScope:fn=>fn({addEventProcessor:fn=>processor=fn}),captureEvent:event=>{captured=processor({...event,user:{email:'private@example.invalid'},request:{url:'private'},breadcrumbs:[{data:'private'}]});setImmediate(()=>callback(event,{statusCode:code}));},flush:async()=>true};
 const context={window:{Sentry},document:{createElement:()=>({style:{},setAttribute(){}})},crypto:{randomUUID:()=> '11111111-1111-4111-8111-111111111111'},setTimeout,clearTimeout};
 if(lazy){let ready;context.window.Sentry={onLoad:fn=>ready=fn,forceLoad:()=>{Object.assign(context.window.Sentry,Sentry);ready();}};}
 vm.createContext(context);vm.runInContext(fs.readFileSync('ui/cecil-error-probe.js','utf8'),context);context.window.bkCecilErrorProbe({append:(...n)=>children.push(...n)});await children[0].onclick();
 assert.equal(captured.user,undefined);assert.equal(captured.request,undefined);assert.equal(captured.breadcrumbs.length,0);assert.equal(captured.message,'CECIL_PILOT_CONTROLLED_TEST');
 assert.equal(children[1].textContent.startsWith('Sentry aceptó'),code===200);assert.equal(children[0].disabled,false);
}
(async()=>{await check(200);await check(503);await check(200,true);console.log('Sentry receipt succeeds only after matching real-transport acceptance; lazy loader supported; probe strips personal data.');})();
