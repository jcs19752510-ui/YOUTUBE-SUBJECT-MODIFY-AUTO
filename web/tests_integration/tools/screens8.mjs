// 실제 Chromium(헤드리스)으로 nginx 경유 화면 8개(홈·영상 목록·영상 상세·배치 목록·배치 상세·이력·리포트·설정)와 없는 주소(404 화면)를 불러
// 제목·핵심 요소·콘솔 오류·CSP 위반·4xx/5xx·외부 요청을 수집한다(7단계 통합 시험, IT-062). 두 가지 화면 폭(1280, 1024)에서 한 번씩 돈다.
// 사용: node screens8.mjs <포트=18080> <결과 JSON 경로> [스크린샷 폴더]
// 전제: 영상이 불러와져 있고 배치가 1개 이상 있어야 상세 화면을 열 수 있다(시험 코드가 준비한다). 저장소에 의존성을 추가하지 않고 전역 playwright(/opt/node22) 를 쓴다.
import { createRequire } from 'node:module';
import fs from 'node:fs';
const require = createRequire('/opt/node22/lib/node_modules/');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '18080';
const OUT = process.argv[3] || '/tmp/screens8.json';
const SHOTS = process.argv[4] || '';
const ORIGIN = 'http://localhost:8080';
const result = { screens: [], console: [], pageerrors: [], csp: [], badResponses: [], thirdParty: [], requests: 0 };

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--no-proxy-server', `--host-resolver-rules=MAP localhost:8080 127.0.0.1:${PORT}`] });

for (const width of [1280, 1024]) {
  const ctx = await browser.newContext({ viewport: { width, height: 800 }, locale: 'ko-KR' });
  await ctx.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(`${e.violatedDirective}|${e.blockedURI}`));
  });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) result.console.push(`${width}: ${m.type()}: ${m.text()}`.slice(0, 300)); });
  page.on('pageerror', (e) => result.pageerrors.push(`${width}: ${String(e).slice(0, 300)}`));
  page.on('request', (r) => { result.requests++; if (!r.url().startsWith(ORIGIN)) result.thirdParty.push(r.url().slice(0, 120)); });
  page.on('response', (r) => { if (r.status() >= 400) result.badResponses.push(`${width}: ${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });

  await page.goto(ORIGIN + '/', { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: '홈', exact: true }).waitFor({ timeout: 15000 });
  // 상세 화면에 쓸 식별자는 화면과 같은 경로(쿠키 세션)로 API 에서 읽는다.
  const ids = await page.evaluate(async () => {
    const v = await (await fetch('/api/v1/videos?page=1&page_size=1')).json();
    const b = await (await fetch('/api/v1/batches')).json();
    const list = Array.isArray(b) ? b : (b.items || []);
    return { video: v.items && v.items[0] ? v.items[0].video_id : null, batch: list[0] ? list[0].id : null };
  });
  const routes = [
    ['홈', '/', /홈/],
    ['영상 목록', '/videos', /영상 목록/],
    ['영상 상세', ids.video ? `/videos/${ids.video}` : null, null],
    ['배치 목록', '/batches', /배치/],
    ['배치 상세', ids.batch != null ? `/batches/${ids.batch}` : null, null],
    ['이력', '/history', /이력/],
    ['리포트', '/reports', /리포트|성과/],
    ['설정', '/settings', /설정/],
    ['없는 화면(404)', '/no-such-screen', null],
  ];
  for (const [name, path, headingRe] of routes) {
    const rec = { width, name, path, ok: false, detail: '' };
    if (path === null) { rec.detail = '식별자 없음(시험 준비 부족)'; result.screens.push(rec); continue; }
    try {
      await page.goto(`${ORIGIN}/#${path}`, { waitUntil: 'networkidle' });
      const h1 = page.getByRole('heading', { level: 1 }).first();
      await h1.waitFor({ timeout: 15000 });
      const title = (await h1.innerText()).trim();
      const body = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
      const noError = !/오류가 발생|알 수 없는 오류|Something went wrong|undefined|\[object Object\]|NaN/.test(body);
      const nav = await page.getByRole('navigation').count();
      const overflowX = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      rec.title = title; rec.bodyChars = body.length; rec.nav = nav; rec.overflowX = overflowX;
      rec.ok = noError && body.length > 40 && (headingRe ? headingRe.test(title) : true);
      rec.detail = rec.ok ? '' : `제목=${title} 본문 앞부분=${body.slice(0, 120)}`;
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/s8-${width}-${String(result.screens.length).padStart(2, '0')}.png`, fullPage: true });
    } catch (e) {
      rec.detail = String(e).split('\n')[0].slice(0, 200);
    }
    result.screens.push(rec);
  }
  result.csp.push(...(await page.evaluate(() => window.__csp).catch(() => [])));
  await ctx.close();
}
await browser.close();
// 의도한 4xx: 없는 화면은 클라이언트 라우팅이라 서버 4xx 가 없어야 한다(그대로 기록).
fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
const failed = result.screens.filter((s) => !s.ok);
for (const s of result.screens) console.log(s.ok ? 'OK  ' : 'FAIL', s.width, s.name, s.title || '', s.detail || '');
console.log(JSON.stringify({ screens: result.screens.length, failed: failed.length, console: result.console.length, pageerrors: result.pageerrors.length, csp: result.csp.length, bad4xx5xx: result.badResponses.length, thirdParty: result.thirdParty.length, requests: result.requests }));
process.exit(failed.length || result.console.length || result.pageerrors.length || result.csp.length || result.badResponses.length || result.thirdParty.length ? 1 : 0);
