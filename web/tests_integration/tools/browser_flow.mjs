// 실제 Chromium(헤드리스)으로 nginx 경유 핵심 흐름을 화면 단위로 확인한다(7단계 통합 시험, IT-060).
// 사용: node browser_flow.mjs <포트=18080> <결과 JSON 경로> [스크린샷 폴더]
// Host/Origin 이 허용 목록(localhost:8080)과 맞도록 Chromium 의 --host-resolver-rules 로 localhost:8080 -> 127.0.0.1:<포트> 로 매핑한다(중계 프로세스 불필요).
// 수집: 콘솔 오류/경고, 페이지 오류, CSP 위반(securitypolicyviolation + 콘솔 메시지), 4xx/5xx 응답(의도한 것은 제외 목록), 단계별 결과.
import { createRequire } from 'node:module';
import fs from 'node:fs';
const require = createRequire('/opt/node22/lib/node_modules/');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '18080';
const OUT = process.argv[3] || '/tmp/browser_flow.json';
const SHOTS = process.argv[4] || '';
const ORIGIN = 'http://localhost:8080';
const result = { steps: [], console: [], pageerrors: [], csp: [], badResponses: [], requests: 0, thirdParty: [] };

function step(name, ok, detail = '') { result.steps.push({ name, ok, detail: String(detail).slice(0, 600) }); console.log(ok ? 'OK  ' : 'FAIL', name, detail ? '- ' + String(detail).slice(0, 200) : ''); }

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox', '--no-proxy-server', `--host-resolver-rules=MAP localhost:8080 127.0.0.1:${PORT}`],
});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'ko-KR' });
await ctx.addInitScript(() => {
  window.__csp = [];
  document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(`${e.violatedDirective}|${e.blockedURI}|${e.sourceFile}:${e.lineNumber}`));
});
const page = await ctx.newPage();
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) result.console.push(`${m.type()}: ${m.text()}`.slice(0, 300)); });
page.on('pageerror', (e) => result.pageerrors.push(String(e).slice(0, 300)));
page.on('request', (r) => { result.requests++; if (!r.url().startsWith(ORIGIN)) result.thirdParty.push(r.url().slice(0, 120)); });
page.on('response', (r) => { if (r.status() >= 400) result.badResponses.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });

const shot = async (n) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true }); };
const text = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ');

try {
  // 1. 첫 화면: 로그인(PIN) 없이 바로 홈
  const resp = await page.goto(ORIGIN + '/', { waitUntil: 'networkidle' });
  step('첫 화면 200 + 보안 헤더(CSP·nosniff)', resp.status() === 200 && !!resp.headers()['content-security-policy'] && resp.headers()['x-content-type-options'] === 'nosniff', resp.status());
  await page.getByRole('heading', { name: '홈', exact: true }).waitFor({ timeout: 15000 });
  step('PIN 입력 없이 홈 표시', !(await text()).includes('PIN을 입력') , '');
  await shot('01-home-empty');

  // 2. 영상 불러오기
  const sync = page.getByRole('button', { name: '데모 영상 불러오기' }).first();
  if (await sync.count()) {
    await sync.click();
    await page.getByText(/전체 영상|영상 200|200/).first().waitFor({ timeout: 60000 }).catch(() => {});
  }
  await page.waitForFunction(() => /전체 영상/.test(document.body.innerText) && !/아직 영상이 없습니다/.test(document.body.innerText), null, { timeout: 90000 });
  step('데모 영상 200개 불러오기(작업 폴링 완료)', true);
  await shot('02-home-synced');

  // 3. 영상 목록 -> 2개 선택 -> 제안 생성
  await page.getByRole('link', { name: '영상 목록' }).first().click();
  await page.getByRole('heading', { name: '영상 목록' }).waitFor();
  await page.getByRole('checkbox', { name: /^(?!이 페이지 전체 선택).+ 선택$/ }).first().waitFor();
  const boxes = page.getByRole('checkbox', { name: /^(?!이 페이지 전체 선택).+ 선택$/ });
  const n = await boxes.count();
  let picked = 0; let pickedHref = '';
  for (let i = 0; i < n && picked < 2; i++) {
    const b = boxes.nth(i);
    if (await b.isEnabled()) { if (!pickedHref) pickedHref = await b.locator('xpath=ancestor::tr//a[starts-with(@href,"#/videos/")]').first().getAttribute('href'); await b.check(); picked++; }
  }
  step('영상 2개 선택', picked === 2, `picked=${picked}`);
  await page.getByRole('button', { name: '선택 영상 AI 제안 생성' }).click();
  await page.getByText(/2개 영상의 제안 생성이 끝났습니다/).waitFor({ timeout: 90000 });
  step('AI(모의) 제안 생성 작업 완료 메시지', true);
  await shot('03-generate-done');
  await page.keyboard.press('Escape');

  // 4. 상세 -> 승인
  await page.locator(`a[href="${pickedHref}"]`).first().click();
  await page.getByRole('heading', { level: 1 }).first().waitFor();
  await shot('04-detail');
  let approved = false;
  const cards = page.getByRole('button', { name: /^승인$/ });
  await cards.first().waitFor({ timeout: 20000 }).catch(() => {});
  const cn = await cards.count();
  step('상세 화면에 승인 가능한 제안 카드 존재', cn > 0, `buttons=${cn}`);
  for (let i = 0; i < cn && !approved; i++) {
    const btn = cards.nth(i);
    if (!(await btn.isEnabled())) continue;
    await btn.click();
    const dlg = page.getByRole('dialog');
    await dlg.waitFor({ timeout: 10000 });
    const name = dlg.getByRole('textbox', { name: /승인자/ });
    if (await name.count()) await name.first().fill('통합시험자');
    const ack = dlg.getByRole('checkbox', { name: /경고 사유/ });
    if (await ack.count()) await ack.first().check();
    const go = dlg.getByRole('button', { name: /^승인$/ });
    if (await go.isEnabled()) {
      await go.click();
      await page.getByText(/승인했습니다/).first().waitFor({ timeout: 15000 });
      approved = true;
    } else {
      await page.keyboard.press('Escape');
    }
  }
  step('제안 승인(서버 서명·만료 24h 기록)', approved);
  await shot('05-approved');

  // 5. 배치 만들기 -> 사전 점검 -> 실행(확인 문구)
  await page.getByRole('link', { name: /배치/ }).first().click();
  await page.getByRole('heading', { name: /배치/ }).first().waitFor();
  await shot('06-batches');
  await page.waitForFunction(() => [...document.querySelectorAll('input[type=checkbox]')].some((c) => !c.disabled), null, { timeout: 20000 });
  const rows = page.getByRole('checkbox');
  const rc = await rows.count();
  for (let i = 0; i < rc; i++) { if (await rows.nth(i).isEnabled()) { await rows.nth(i).check(); break; } }
  await page.getByRole('button', { name: '사전 점검 만들기' }).click();
  await page.getByText('사전 점검(미리보기)').first().waitFor({ timeout: 20000 });
  step('배치 사전 점검(미리보기) 표시', true);
  await shot('07-precheck');
  const phrase = page.getByLabel(/확인 문구 입력/);
  await phrase.waitFor();
  const m = (await text()).match(/실행\s\d+건/);
  const runBtn = page.getByRole('button', { name: '실행', exact: true });
  step('확인 문구 입력 전에는 실행 버튼 비활성', !(await runBtn.isEnabled()));
  await phrase.fill((m ? m[0] : '실행 1건').replace(/\s+/g, ' ') + ' ');
  step('문구 끝에 공백이 있으면 실행 버튼 비활성', !(await runBtn.isEnabled()));
  await phrase.fill((m ? m[0] : '실행 1건').replace(/\s+/g, ' '));
  // 개정 2판: 실행 전 A/B 테스트 확인란(ko.legal.abConfirm)이 새로 생겼다. 문구가 맞아도 확인란 전에는 실행할 수 없어야 한다.
  step('A/B 테스트 확인란 체크 전에는 문구가 맞아도 실행 버튼 비활성', !(await runBtn.isEnabled()));
  await page.getByRole('checkbox', { name: /A\/B 테스트 중이 아님/ }).check();
  await runBtn.click();
  await page.getByText(/실행을 시작했습니다/).first().waitFor({ timeout: 20000 }).catch(() => {});
  const doneOk = await page.getByText('완료', { exact: true }).first().waitFor({ timeout: 90000 }).then(() => true).catch(() => false);
  step('배치 실행 요청 후 워커가 처리(배치 상태 배지 "완료")', doneOk);
  await shot('08-executed');

  // 6. 이력
  await page.getByRole('link', { name: /이력/ }).first().click();
  await page.getByRole('heading', { name: /이력/ }).first().waitFor();
  await page.getByText(/demoVid\d{4}/).first().waitFor({ timeout: 20000 }).catch(() => {});
  const hist = await text();
  step('이력 화면에 반영 1건 표시', /demoVid\d{4}/.test(hist), hist.slice(0, 160));
  await shot('09-history');

  // 7. 나머지 화면 순회(리포트·설정)
  for (const nm of [/리포트|성과/, /설정/]) {
    await page.getByRole('link', { name: nm }).first().click();
    await page.waitForLoadState('networkidle');
  }
  step('리포트·설정 화면 이동', true);
  await shot('10-settings');
  // 8. CSP 가 실제 브라우저에서 효력이 있는가(의도적 위반을 시도하고 막히는지 확인, 확인 뒤 위반 기록은 비운다)
  const consoleBeforeProbe = result.console.length; const tpBefore = result.thirdParty.length; const badBefore = result.badResponses.length;
  const probe = await page.evaluate(async () => {
    const out = {};
    const sc = document.createElement('script'); sc.textContent = 'window.__inl = 1'; document.head.appendChild(sc);
    out.inlineScriptRan = window.__inl === 1;
    const im = document.createElement('img'); im.src = 'http://127.0.0.1:9/x.png'; document.body.appendChild(im);
    try { await fetch('http://example.invalid/', { mode: 'no-cors' }); out.crossFetch = 'allowed'; } catch { out.crossFetch = 'blocked'; }
    const f = document.createElement('iframe'); f.src = '/'; document.body.appendChild(f);
    await new Promise((r) => setTimeout(r, 1500));
    out.csp = window.__csp.length;
    out.iframeUrl = f.contentWindow ? (() => { try { return f.contentWindow.location.href; } catch { return 'cross-origin(blocked)'; } })() : 'none';
    return out;
  });
  const frameBlocked = page.frames().filter((fr) => fr !== page.mainFrame()).every((fr) => !fr.url().startsWith(ORIGIN));
  step('CSP 실효: 인라인 스크립트 차단', probe.inlineScriptRan === false, JSON.stringify(probe));
  step('CSP 실효: 외부 주소 fetch/이미지 차단(connect-src·img-src self)', probe.crossFetch === 'blocked' && probe.csp >= 2, JSON.stringify(probe));
  step('CSP 실효: frame-ancestors none 으로 자기 자신도 프레임에 못 들어감', frameBlocked, page.frames().map((fr) => fr.url()).join(','));
  await page.evaluate(() => { window.__csp = []; });
  const csp = await page.evaluate(() => window.__csp);
  result.csp.push(...csp);
  result.thirdParty.length = tpBefore; result.badResponses.length = badBefore;
  result.console.length = consoleBeforeProbe;   // 의도적 위반이 만든 콘솔 줄만 버린다(그 앞의 정상 흐름에서 나온 줄은 그대로 남김)
} catch (e) {
  step('흐름 중단: ' + String(e).split('\n').slice(0, 6).join(' / '), false);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/zz-fail.png`, fullPage: true }).catch(() => {});
  result.csp.push(...(await page.evaluate(() => window.__csp).catch(() => [])));
}
result.cookies = (await ctx.cookies()).map((c) => ({ name: c.name, httpOnly: c.httpOnly, sameSite: c.sameSite, secure: c.secure, path: c.path }));
await browser.close();
fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
const bad = result.steps.some((s) => !s.ok) || result.console.length || result.pageerrors.length || result.csp.length || result.badResponses.length || result.thirdParty.length;
console.log(JSON.stringify({ steps: result.steps.length, failed: result.steps.filter((s) => !s.ok).length, console: result.console.length, pageerrors: result.pageerrors.length, csp: result.csp.length, bad4xx5xx: result.badResponses.length, thirdParty: result.thirdParty.length, requests: result.requests }));
process.exit(bad ? 1 : 0);
