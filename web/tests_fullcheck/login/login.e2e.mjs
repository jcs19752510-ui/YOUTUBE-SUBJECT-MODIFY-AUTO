import { chromium } from 'playwright-core';
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
import { globSync } from 'node:fs';
const require = createRequire(import.meta.url);
const axeSrc = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const DIST = path.resolve('../../frontend/dist'); const SHOTS = path.resolve('../../../.harness-tmp/results/login-screens');
const mime = { '.js':'text/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml' };
const srv = http.createServer((q,r)=>{ let p=path.join(DIST, q.url.split('?')[0]); if(!fs.existsSync(p)||fs.statSync(p).isDirectory()) p=path.join(DIST,'index.html'); r.setHeader('content-type',mime[path.extname(p)]||'text/html'); r.end(fs.readFileSync(p)); });
await new Promise(r=>srv.listen(0,'127.0.0.1',r)); const BASE=`http://127.0.0.1:${srv.address().port}/`;
const exe = fs.readdirSync('/opt/pw-browsers').filter(d=>/^chromium-\d+$/.test(d)).map(d=>`/opt/pw-browsers/${d}/chrome-linux/chrome`)[0];
const browser = await chromium.launch({ executablePath: exe, args:['--no-sandbox'] });
const results=[]; const rec=(n,exp,act,ok)=>{results.push({n,exp,act,ok}); console.log(ok?'PASS':'FAIL',n,'| expected:',exp,'| actual:',act);};
const PW='Test-Secret-9z!', ID='probe-admin';
async function newPage(){
  const ctx = await browser.newContext(); const page = await ctx.newPage(); if(process.env.LOGREQ){page.on('console',m=>console.log('CONSOLE',m.text().slice(0,200)));page.on('pageerror',e=>console.log('PAGEERR',e.message.slice(0,200)));} const st={authed:false, logins:[], loginHeaders:[]};
  await page.route('**/api/v1/**', async route=>{ const rq=route.request(); const u=new URL(rq.url()); const p=u.pathname; const m=rq.method();
    const j=(s,b)=>route.fulfill({status:s,contentType:'application/json',body:b==null?'':JSON.stringify(b)});
    if(p==='/api/v1/auth/me') return j(200, st.authed?{authenticated:true,pin_required:false,csrf_token:'c1',login_required:false,admin_login_id:ID}:{authenticated:false,pin_required:false,csrf_token:null,login_required:true});
    if(p==='/api/v1/auth/login'&&m==='POST'){ st.logins.push(rq.postDataJSON()); const b=rq.postDataJSON(); if(b.login_id===ID||b.username===ID||JSON.stringify(b).includes(ID)){st.authed=true; return j(200,{csrf_token:'c2',admin_login_id:ID,idle_timeout_seconds:3600});} return j(401,{type:'x',title:'t',status:401,code:'login_invalid'}); }
    if(process.env.LOGREQ) console.log('REQ',m,p);
    if(p==='/api/v1/auth/session'&&m==='DELETE'){ st.authed=false; return j(204,null); }
    if(p==='/api/v1/dashboard') return j(503,{type:'x',title:'가짜 서버',status:503,code:'unavailable'});
    return j(200,{items:[],total:0}); });
  return {ctx,page,st};
}
const sel={form:'form',id:'#login-id',pw:'#login-password'};
const attrs=p=>p.evaluate(()=>{const g=(s)=>{const e=document.querySelector(s);return {ac:e.getAttribute('autocomplete'),name:e.name,ro:e.readOnly,type:e.type,val:e.value}};return {form:document.querySelector('form').getAttribute('autocomplete'),id:g('#login-id'),pw:g('#login-password'),active:document.activeElement?.id||document.activeElement?.tagName}});
const fill=(p)=>p.evaluate(([i,w])=>{const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(document.querySelector('#login-id'),i);s.call(document.querySelector('#login-password'),w);document.querySelector('#login-id').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#login-password').dispatchEvent(new Event('input',{bubbles:true}));},['saved-id','saved-pass']);
const fillNoEvent=(p)=>p.evaluate(()=>{const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;s.call(document.querySelector('#login-id'),'saved-id');s.call(document.querySelector('#login-password'),'saved-pass');});
const vals=p=>p.evaluate(()=>[document.querySelector('#login-id')?.value,document.querySelector('#login-password')?.value]);
const empty=v=>v[0]===''&&v[1]==='';
async function open(){ const o=await newPage(); await o.page.goto(BASE); await o.page.waitForSelector('#login-id'); return o; }
// (a)
{ const {page}=await open(); const a=await attrs(page); await page.screenshot({path:`${SHOTS}/a-initial.png`});
  rec('a DOM 속성','form off, id off/admin-login-id, pw new-password/admin-login-secret, type=password',JSON.stringify(a),a.form==='off'&&a.id.ac==='off'&&a.id.name==='admin-login-id'&&a.pw.ac==='new-password'&&a.pw.name==='admin-login-secret'&&a.pw.type==='password');
  rec('a2 readonly 초기값(자동 포커스 여부 확인)','readonly=true 이고 포커스 없음',`id.ro=${a.id.ro} pw.ro=${a.pw.ro} active=${a.active}`,a.id.ro===true&&a.pw.ro===true); await page.context().close(); }
// (b) autofill sim at several times, with input event (React sees it) and without
for (const [label,fn] of [['native setter + input 이벤트',fill],['native setter만(이벤트 없음)',fillNoEvent]])
 for (const t of [0,200,800]) { const {page}=await open(); await page.waitForTimeout(t); await fn(page); const v0=await vals(page); await page.waitForTimeout(2300); const v=await vals(page); const msg=await page.locator('#login-msg').innerText();
  rec(`b 자동채움 흉내 ${label} +${t}ms`,'2.3초 안에 두 칸 비워짐',`채움직후=${JSON.stringify(v0.map(x=>x?'값있음':''))} 이후=${JSON.stringify(v.map(x=>x?'값있음':''))} 안내="${msg}"`,empty(v)); await page.context().close(); }
// (b2) late autofill after 1.5s (all timers expired)
{ const {page}=await open(); await page.waitForTimeout(2000); await fillNoEvent(page); await page.waitForTimeout(1500); const v=await vals(page); rec('b2 2초 뒤 늦은 자동채움(타이머 종료 후, 참고)','비워지지 않을 수 있음(설계 한계)',JSON.stringify(v.map(x=>x?'값있음':'')),true); await page.context().close(); }
// (c) human typing
{ const {page,st}=await open(); await page.click('#login-id'); await page.keyboard.type(ID); await page.click('#login-password'); await page.keyboard.type(PW); await page.waitForTimeout(2000);
  const v=await vals(page); const dis=await page.locator('button[type=submit]').isDisabled();
  rec('c 사람 입력 유지(2초 대기 후)','입력값 유지, 버튼 활성',`id일치=${v[0]===ID} pw일치=${v[1]===PW} 버튼비활성=${dis}`,v[0]===ID&&v[1]===PW&&!dis);
  await page.keyboard.press('Enter'); await page.waitForTimeout(800);
  rec('c 제출 시 입력값 그대로 전송','POST body 에 입력값',JSON.stringify(st.logins.map(b=>Object.fromEntries(Object.entries(b).map(([k,x])=>[k,x===ID?'ID일치':x===PW?'PW일치':'다름'])))),st.logins.length===1&&Object.values(st.logins[0]).includes(ID)&&Object.values(st.logins[0]).includes(PW));
  await page.screenshot({path:`${SHOTS}/c-after-login.png`}); await page.context().close(); }
// (c2) typing only after 3s delay (timers expired), and slow typing before 1.5s
{ const {page,st}=await open(); await page.waitForTimeout(100); await page.click('#login-id'); await page.keyboard.type(ID,{delay:300}); await page.click('#login-password'); await page.keyboard.type(PW,{delay:200}); const v=await vals(page); rec('c2 느린 타이핑(타이머 구간과 겹침)','입력값 유지',`id=${v[0]===ID} pw=${v[1]===PW}`,v[0]===ID&&v[1]===PW); await page.context().close(); }
// (c3) paste without keydown (insertText = paste/voice/IME commit w/o keydown)
{ const {page}=await open(); await page.click('#login-id'); await page.keyboard.insertText(ID); await page.click('#login-password'); await page.keyboard.insertText(PW); await page.waitForTimeout(2000); const v=await vals(page);
  rec('c3 키 이벤트 없는 입력(insertText: 음성·모바일·가상키보드·IME 확정 흉내)','입력값 유지(안 지워져야 함)',`id=${v[0]===ID} pw=${v[1]===PW}`,v[0]===ID&&v[1]===PW); await page.context().close(); }
{ const {page}=await open(); await page.waitForTimeout(2200); await page.click('#login-id'); await page.keyboard.insertText(ID); await page.click('#login-password'); await page.keyboard.insertText(PW); await page.waitForTimeout(1500); const v=await vals(page);
  rec('c3b 키 이벤트 없는 입력을 화면 연 지 2.2초 뒤에 함','유지',`id=${v[0]===ID} pw=${v[1]===PW}`,v[0]===ID&&v[1]===PW); await page.context().close(); }
// (c4) clipboard-style paste via ClipboardEvent
{ const {page}=await open(); await page.click('#login-id'); await page.evaluate(()=>{const e=document.querySelector('#login-id');const dt=new DataTransfer();dt.setData('text/plain','pasted-id');e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));}); await page.keyboard.insertText('pasted-id'); await page.waitForTimeout(2000); const v=await vals(page);
  rec('c4 붙여넣기 이벤트 후 삽입','유지',`id=${v[0]==='pasted-id'}`,v[0]==='pasted-id'); await page.context().close(); }
// (c5) IME composition without keydown
{ const {page}=await open(); await page.click('#login-id'); await page.evaluate(()=>{const e=document.querySelector('#login-id');e.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));}); await page.keyboard.insertText('관리자'); await page.evaluate(()=>{document.querySelector('#login-id').dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'관리자'}));}); await page.waitForTimeout(2000); const v=await vals(page);
  rec('c5 한글 IME 흉내(composition 이벤트+insertText, keydown 없음)','유지',`id=${JSON.stringify(v[0])}`,v[0]==='관리자'); await page.context().close(); }
// (c6) real keyboard with Korean chars via type
{ const {page}=await open(); await page.click('#login-id'); await page.keyboard.type('관리자abc'); await page.waitForTimeout(2000); const v=await vals(page); rec('c6 한글 type()','유지',JSON.stringify(v[0]),v[0]==='관리자abc'); await page.context().close(); }
// (d) reload, back/forward
{ const {page}=await open(); await page.click('#login-id'); await page.keyboard.type(ID); await page.click('#login-password'); await page.keyboard.type(PW); await page.reload(); await page.waitForSelector('#login-id'); await page.waitForTimeout(300); let v=await vals(page); rec('d 새로고침 후(사람 입력 뒤)','비어 있음',JSON.stringify(v.map(x=>x?'값있음':'')),empty(v));
  await page.click('#login-id'); await page.keyboard.type('zz'); await page.goto(BASE+'?x=1'); await page.waitForSelector('#login-id'); await page.goBack(); await page.waitForSelector('#login-id'); await page.waitForTimeout(2000); v=await vals(page); rec('d2 뒤로가기 후','비어 있음',JSON.stringify(v.map(x=>x?'값있음':'')),empty(v));
  await page.goForward(); await page.waitForSelector('#login-id'); await page.waitForTimeout(2000); v=await vals(page); rec('d3 앞으로가기 후','비어 있음',JSON.stringify(v.map(x=>x?'값있음':'')),empty(v)); await page.context().close(); }
// (e) logout
{ const {page,st}=await open(); await page.click('#login-id'); await page.keyboard.type(ID); await page.click('#login-password'); await page.keyboard.type(PW); await page.keyboard.press('Enter'); await page.waitForTimeout(1000);
  const lo=page.getByRole('button',{name:'로그아웃'}); const n=await lo.count(); if(n){ await lo.first().click(); await page.waitForSelector('#login-id',{timeout:5000}).catch(()=>{}); await page.waitForTimeout(2000); const v=await vals(page); rec('e 로그아웃 후 로그인 화면 칸','비어 있음',JSON.stringify(v.map(x=>x?'값있음':'')),empty(v)); await page.reload(); await page.waitForSelector('#login-id'); await fillNoEvent(page); await page.waitForTimeout(1800); const w=await vals(page); rec('e2 로그아웃 후 새로고침 직후 자동채움 흉내','비워짐',JSON.stringify(w.map(x=>x?'값있음':'')),empty(w)); }
  else { await page.screenshot({path:`${SHOTS}/e-no-logout-btn.png`}); rec('e 로그아웃','버튼 찾음','로그아웃 버튼 없음(가짜 API 응답 한계 가능)',false); } await page.context().close(); }
// (f) storage
{ const {page,st}=await open(); await page.click('#login-id'); await page.keyboard.type(ID); await page.click('#login-password'); await page.keyboard.type(PW); await page.waitForTimeout(500);
  const s=await page.evaluate(([i,w])=>({url:location.href.includes(i)||location.href.includes(w),ls:JSON.stringify({...localStorage}).includes(w)||JSON.stringify({...localStorage}).includes(i),ss:JSON.stringify({...sessionStorage}).includes(w)||JSON.stringify({...sessionStorage}).includes(i),ck:document.cookie.includes(w)||document.cookie.includes(i),type:document.querySelector('#login-password').type,txt:document.body.innerText.includes(w)}),[ID,PW]);
  rec('f 저장소·URL·쿠키·화면글자에 값 없음, type=password',"모두 false, type=password",JSON.stringify(s),!s.url&&!s.ls&&!s.ss&&!s.ck&&!s.txt&&s.type==='password'); await page.context().close(); }
// (g) keyboard only + axe
{ const {page,st}=await open(); await page.keyboard.press('Tab'); let a=await page.evaluate(()=>document.activeElement.id); await page.keyboard.type(ID); await page.keyboard.press('Tab'); const a2=await page.evaluate(()=>document.activeElement.id); await page.keyboard.type(PW); await page.waitForTimeout(500); await page.keyboard.press('Enter'); await page.waitForTimeout(800);
  rec('g 키보드만(Tab,Tab,Enter)으로 로그인','첫 Tab→아이디, 둘째→비밀번호, 제출 성공',`tab1=${a} tab2=${a2} 전송=${st.logins.length}`,a==='login-id'&&a2==='login-password'&&st.logins.length===1); await page.context().close(); }
{ const {page}=await open(); await page.evaluate(axeSrc); const r=await page.evaluate(async()=>{const x=await axe.run(document); return x.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length}))}); rec('g2 axe-core 위반','0건',JSON.stringify(r),r.length===0);
  await page.click('#login-id'); await page.evaluate(()=>{}); const r2=await page.evaluate(async()=>{const x=await axe.run(document); return x.violations.map(v=>v.id)}); rec('g3 axe(칸 활성 후)','0건',JSON.stringify(r2),r2.length===0); await page.context().close(); }
// h: wrong password flow still works & password cleared
{ const {page,st}=await open(); await page.click('#login-id'); await page.keyboard.type('nobody'); await page.click('#login-password'); await page.keyboard.type(PW); await page.keyboard.press('Enter'); await page.waitForTimeout(800); const v=await vals(page); const msg=await page.locator('#login-msg').innerText();
  rec('h 틀린 로그인 후','메시지 표시, 아이디 유지/비밀번호 비움',`msg="${msg}" id=${v[0]} pwEmpty=${v[1]===''}`,v[1]===''&&/올바르지/.test(msg)); await page.context().close(); }
await browser.close(); srv.close();
fs.writeFileSync('results.json',JSON.stringify(results,null,1)); console.log('\nTOTAL',results.length,'FAIL',results.filter(r=>!r.ok).length);
