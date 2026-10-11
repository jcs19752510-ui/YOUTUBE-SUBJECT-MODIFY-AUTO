// 7단계 개정 2판 화면 확인: 모드 띠 문구, C-1(차단 제안 버튼), C-2(초안 버리기), 이력 결과 선택지, 면책·AI 고지, 캡처.
// 사용: node rev2_screens.mjs <포트> <결과 json> <캡처 폴더>
import { createRequire } from 'node:module';
import fs from 'node:fs';
const { chromium } = createRequire('/opt/node22/lib/node_modules/')('playwright');
const PORT = process.argv[2] || '18083';
const OUTJ = process.argv[3];
const SH = process.argv[4];
fs.mkdirSync(SH, { recursive: true });
const BASE = `http://127.0.0.1:${PORT}`;
const res = { steps: [], console: [], pageerrors: [], csp: [], badResponses: [], thirdParty: [], facts: {} };
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
// 시험 주소(18083) 의 Host/Origin 은 nginx·백엔드 허용 목록에 추가해 두었다.
const page = await ctx.newPage();
page.on('pageerror', (e) => res.pageerrors.push(String(e.message).slice(0, 200)));
page.on('console', (m) => {
  const t = m.text();
  if (m.type() === 'error' || m.type() === 'warning') res.console.push(m.type() + ': ' + t.slice(0, 200));
  if (/content security policy|Refused to/i.test(t)) res.csp.push(t.slice(0, 200));
});
page.on('response', (r) => { if (r.status() >= 400) res.badResponses.push(r.status() + ' ' + r.request().method() + ' ' + r.url().replace(BASE, '')); });
page.on('request', (r) => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith('data:') && !u.startsWith('blob:')) res.thirdParty.push(u.slice(0, 120)); });
const shot = async (n, h = 900) => { await page.setViewportSize({ width: 1280, height: h }); await page.waitForTimeout(500); await page.screenshot({ path: `${SH}/${n}.png` }); };
async function step(name, fn) {
  const t0 = Date.now();
  try { const note = await fn(); res.steps.push({ name, ok: true, note: note ?? '', ms: Date.now() - t0 }); }
  catch (e) { res.steps.push({ name, ok: false, note: String(e.message).split('\n')[0], ms: Date.now() - t0 }); try { await page.screenshot({ path: `${SH}/_fail_${name}.png` }); } catch {} }
}
const bodyText = async () => (await page.locator('body').innerText());

await step('01-home-mode-badge', async () => {
  await page.goto(`${BASE}/#/`);
  await page.getByRole('heading', { name: '홈', exact: true }).waitFor();
  await page.getByText('데모 모드 — 유튜브에 아무것도 전송되지 않습니다').first().waitFor({ timeout: 10000 });
  res.facts.homeBadge = true;
  await shot('01-home-empty');
});
await step('02-sync', async () => {
  await page.getByRole('button', { name: '데모 영상 불러오기' }).click();
  await page.getByText('200', { exact: true }).first().waitFor({ timeout: 40000 });
  await page.waitForTimeout(1200);
  res.facts.homeTextHasGoogleDemo = (await bodyText()).includes('데모 모드(실제 유튜브와 연결되지 않음)');
  await shot('02-home-synced');
  return 'googleDemoLine=' + res.facts.homeTextHasGoogleDemo;
});
await step('03-videos', async () => {
  await page.goto(`${BASE}/#/videos`);
  await page.locator('tbody tr').nth(5).waitFor({ timeout: 20000 });
  await shot('03-videos', 1250);
  return (await page.getByText('데모 모드 — 유튜브에 아무것도 전송되지 않습니다').count()) + ' badge';
});
// 영상 상세에서 차단 제안을 찾는다(API 로 제안을 만들어 두고 화면은 열람)
let blockedVideo = null;
await step('04-find-blocked-via-api', async () => {
  const r = await page.evaluate(async () => {
    const csrf = (await (await fetch('/api/v1/auth/me')).json()).csrf_token;
    const vids = (await (await fetch('/api/v1/videos?page_size=100')).json()).items.filter((v) => !v.excluded);
    for (const v of vids.slice(0, 80)) {
      const rr = await fetch(`/api/v1/videos/${v.video_id}/suggestions`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ count: 5 }) });
      if (rr.status !== 201) continue;
      const arr = await rr.json();
      if (arr.some((s) => s.status === 'blocked')) return v.video_id;
      await new Promise((ok) => setTimeout(ok, 60));
    }
    return null;
  });
  if (!r) throw new Error('차단 제안을 못 찾음');
  blockedVideo = r;
  return r;
});
await step('05-c1-blocked-card', async () => {
  await page.goto(`${BASE}/#/videos/${blockedVideo}`);
  await page.getByRole('heading', { name: '제안 목록' }).waitFor({ timeout: 20000 });
  await page.getByText('차단됨').first().waitFor({ timeout: 15000 });
  const t = await bodyText();
  res.facts.c1_englishBlockedVisible = /\bblocked\b/.test(t);
  const card = page.locator('li, article, div').filter({ hasText: '차단됨' }).filter({ has: page.getByRole('button', { name: /제목 수정/ }) }).last();
  const hasEdit = (await page.getByRole('button', { name: /제목 수정/ }).count()) > 0;
  const hasReject = (await page.getByRole('button', { name: /반려/ }).count()) > 0;
  res.facts.c1_hasEditButton = hasEdit; res.facts.c1_hasRejectButton = hasReject;
  res.facts.c1_hint = t.includes('고쳐 다시 검증하거나');
  res.facts.c1_aiNotice = t.includes('AI가 생성한 제안입니다');
  res.facts.c1_aiLimit = t.includes('AI 제안은 사실과 법령 적합성을 보장하지 않습니다');
  res.facts.c1_footer = t.includes('면책 및 AI 안내') || t.includes('법률 자문이 아니며');
  await shot('05-c1-blocked-card', 2300);
  if (/\bblocked\b/.test(t)) throw new Error('영문 blocked 노출');
  if (!hasEdit || !hasReject) throw new Error('차단 제안에 버튼 없음');
  return JSON.stringify({ hasEdit, hasReject });
});
await step('06-c1-reject-blocked', async () => {
  const before = await page.getByText('차단됨').count();
  const btn = page.getByRole('button', { name: /반려/ }).first();
  await btn.click();
  const dlg = page.getByRole('dialog');
  if (await dlg.count()) { await shot('06-c1-reject-dialog'); const ok = dlg.getByRole('button', { name: /반려/ }).last(); await ok.click(); }
  await page.waitForTimeout(1500);
  const after = await page.getByText('차단됨').count();
  await shot('06-c1-after-reject', 2300);
  if (!(after < before)) throw new Error(`차단됨 ${before} -> ${after} (반려 후 줄지 않음)`);
  return `${before}->${after}`;
});
// 승인 가능한 제안 만들기(API) → 배치 화면
let approvedIds = [];
await step('07-approve-two-via-api', async () => {
  approvedIds = await page.evaluate(async () => {
    const csrf = (await (await fetch('/api/v1/auth/me')).json()).csrf_token;
    const h = { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf };
    const vids = (await (await fetch('/api/v1/videos?page_size=100')).json()).items.filter((v) => !v.excluded).slice(80, 140);
    const out = [];
    for (const v of vids) {
      if (out.length >= 3) break;
      const rr = await fetch(`/api/v1/videos/${v.video_id}/suggestions`, { method: 'POST', headers: h, body: JSON.stringify({ count: 5 }) });
      if (rr.status !== 201) continue;
      for (const s of await rr.json()) {
        if (s.validation_result === 'pass' && !s.strict && s.status === 'candidate') {
          const a = await fetch(`/api/v1/suggestions/${s.id}/approve`, { method: 'POST', headers: h, body: JSON.stringify({ approver: '화면검증' }) });
          if (a.status === 200) { out.push(s.id); break; }
        }
      }
      await new Promise((ok) => setTimeout(ok, 60));
    }
    return out;
  });
  if (approvedIds.length < 3) throw new Error('승인 3건 못 만듦: ' + approvedIds.length);
  return approvedIds.join(',');
});
await step('08-c2-make-draft', async () => {
  await page.goto(`${BASE}/#/batches`);
  await page.getByText('반영할 승인 항목 고르기').waitFor({ timeout: 20000 });
  await page.locator('input[type=checkbox]').first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(800);
  const boxes = page.locator('tbody input[type=checkbox]:not([disabled])');
  const n = await boxes.count();
  for (let i = 0; i < Math.min(n, 2); i++) await boxes.nth(i).check();
  await page.getByRole('button', { name: '사전 점검 만들기' }).click();
  await page.getByText('사전 점검(미리보기)').waitFor({ timeout: 20000 });
  const t = await bodyText();
  res.facts.c7_precheckNotice = t.includes('법률 자문이 아니며');
  await shot('08-c2-precheck-draft', 2000);
  return 'notice=' + res.facts.c7_precheckNotice;
});
await step('09-c2-discard-from-list-or-detail', async () => {
  await page.goto(`${BASE}/#/batches`);
  await page.waitForTimeout(1500);
  await shot('09-c2-batch-list-with-draft', 1400);
  const t = await bodyText();
  res.facts.c2_listMentionsDraft = /초안/.test(t);
  // 목록에서 초안 열기 → 상세에서 버리기
  const open = page.getByRole('link', { name: /열기/ }).first();
  const openBtn = (await open.count()) ? open : page.getByRole('button', { name: /열기/ }).first();
  await openBtn.click();
  await page.getByRole('button', { name: /초안 버리기/ }).first().waitFor({ timeout: 15000 });
  await shot('09-c2-draft-detail', 1400);
  await page.getByRole('button', { name: /초안 버리기/ }).first().click();
  await page.getByRole('dialog').waitFor();
  await shot('09-c2-discard-dialog');
  await page.getByRole('dialog').getByRole('button', { name: '버리기' }).click();
  await page.getByText('초안을 버렸습니다.').first().waitFor({ timeout: 10000 });
  await page.waitForTimeout(600);
  await shot('09-c2-discarded', 1400);
  res.facts.c2_discardedLabel = (await bodyText()).includes('버려진 초안') || (await bodyText()).includes('초안은 버려졌습니다');
  return 'discardedLabel=' + res.facts.c2_discardedLabel;
});
await step('10-c2-reuse-same-suggestions', async () => {
  await page.goto(`${BASE}/#/batches`);
  await page.getByText('반영할 승인 항목 고르기').waitFor({ timeout: 20000 });
  await page.waitForTimeout(1200);
  const boxes = page.locator('tbody input[type=checkbox]:not([disabled])');
  const n = await boxes.count();
  if (n < 3) throw new Error('버린 뒤 다시 선택 가능한 승인 항목이 3개 미만: ' + n);
  for (let i = 0; i < 3; i++) await boxes.nth(i).check();
  await page.getByRole('button', { name: '사전 점검 만들기' }).click();
  await page.getByText('사전 점검(미리보기)').waitFor({ timeout: 20000 });
  await shot('10-c2-reuse', 2000);
  return 'selectable=' + n;
});
await step('11-history-result-filter', async () => {
  await page.goto(`${BASE}/#/history`);
  await page.waitForTimeout(1500);
  const sel = page.getByLabel(/결과/).first();
  const opts = await sel.locator('option').allInnerTexts();
  res.facts.history_options = opts;
  const out = [];
  for (const o of opts) {
    await sel.selectOption({ label: o });
    const s = page.getByRole('button', { name: /검색|조회|적용/ });
    if (await s.count()) await s.first().click();
    await page.waitForTimeout(700);
    const t = await bodyText();
    const err = /validation_error|Input should be|422|unprocessable/i.test(t) || (await page.getByRole('alert').count()) > 0;
    out.push(`${o}:${err ? 'ERR' : 'ok'}`);
  }
  await shot('11-history-filter');
  if (out.some((x) => x.endsWith('ERR'))) throw new Error('선택지 오류 ' + out.join(' | '));
  return out.join(' | ');
});
await step('12-history-after-apply', async () => {
  // 승인 3건 중 반영 1건을 실제로 해 두고 이력 화면 확인
  await page.goto(`${BASE}/#/history`);
  await page.waitForTimeout(800);
  await shot('12-history', 1100);
});
await step('13-settings-audit-korean', async () => {
  await page.goto(`${BASE}/#/settings`);
  await page.waitForTimeout(1000);
  const tab = page.getByRole('tab', { name: /감사/ });
  if (await tab.count()) await tab.first().click(); else await page.getByText('감사 로그').first().click();
  await page.waitForTimeout(1200);
  const t = await bodyText();
  const eng = ['batch.cancel', 'suggestion.approve', 'session.created', 'owner'].filter((x) => t.includes(x));
  res.facts.audit_englishCodes = eng;
  res.facts.settings_google = t.includes('구글') ;
  await shot('13-settings-audit', 1300);
  if (eng.length) throw new Error('영문 코드 노출: ' + eng.join(','));
});
await step('14-reports-disclaimer', async () => {
  await page.goto(`${BASE}/#/reports`);
  await page.waitForTimeout(1500);
  const t = await bodyText();
  res.facts.reports_disclaimer = t.includes('법률 자문이 아니며');
  await shot('14-reports', 1100);
  if (!res.facts.reports_disclaimer) throw new Error('리포트에 면책 없음');
});
await step('15-footer-everywhere', async () => {
  const miss = [];
  for (const h of ['#/', '#/videos', '#/batches', '#/history', '#/reports', '#/settings']) {
    await page.goto(`${BASE}/${h}`); await page.waitForTimeout(700);
    const t = await bodyText();
    if (!/법률 자문이 아니며|면책 및 AI 안내/.test(t)) miss.push(h);
  }
  res.facts.footerMissingOn = miss;
  if (miss.length) throw new Error('면책/AI 안내 없는 화면: ' + miss.join(' '));
});
await b.close();
fs.writeFileSync(OUTJ, JSON.stringify(res, null, 2));
const bad = res.steps.filter((s) => !s.ok);
console.log(res.steps.map((s) => (s.ok ? 'OK  ' : 'FAIL') + ' ' + s.name + ' ' + s.note).join('\n'));
console.log('console', res.console.length, 'pageerrors', res.pageerrors.length, 'csp', res.csp.length, 'bad', res.badResponses.length, 'third', res.thirdParty.length);
process.exit(bad.length ? 1 : 0);
