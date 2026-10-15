import { createRequire } from 'node:module';
const { chromium } = createRequire('/opt/node22/lib/node_modules/')('playwright');
const B='http://127.0.0.1:18080';
const br = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await br.newContext({ viewport: { width: 1280, height: 900 } }); const page = await ctx.newPage();
page.on('request', r=>{ if(r.method()!=='GET') console.log(r.method(), r.url()); });
await page.goto(B+'/#/'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(1500);
const vids=(await (await ctx.request.get(B+'/api/v1/videos')).json()).items||[]; console.log('vids',vids.length);
const V=vids.find(v=>!v.excluded&&!(v.exclusion_reasons||[]).length).video_id;
await page.goto(`${B}/#/videos/${V}`); await page.waitForTimeout(2500);
console.log('articles', await page.getByRole('article').count());
if(!(await page.getByRole('article').count())){ await page.getByRole('button',{name:'AI 제안 만들기'}).first().click(); await page.getByText('변경 전/후 비교').first().waitFor({timeout:40000}); }
const card=page.getByRole('article').filter({hasText:'변경 전/후'}).last();
await card.getByRole('button',{name:'제목 수정'}).click(); await page.getByRole('dialog').waitFor();
await page.getByLabel('새 제목').fill('이 영양제로 암 완치 가능합니다');
console.log(await page.getByRole('dialog').innerText());
await page.getByRole('dialog').getByRole('button',{name:/저장/}).click(); await page.waitForTimeout(2500);
await page.screenshot({path:'.harness-tmp/results/g-rerun/dbg.png'}); console.log((await page.locator('body').innerText()).slice(0,600));
await br.close();
