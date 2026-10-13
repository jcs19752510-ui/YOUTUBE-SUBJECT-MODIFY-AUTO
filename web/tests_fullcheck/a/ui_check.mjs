// 8단계 전체 점검 a: 바뀐 화면 판정 + F12 이슈(CDP Audits) + 콘솔/CSP + axe + 키보드 흐름. 소스 수정 없음. 비밀 값 미사용.
// 사용: PHASE=empty|full E2E_BASE=http://127.0.0.1:18080 OUT=<폴더> AXE=<axe.min.js> node ui_check.mjs
import { createRequire } from 'node:module';
import fs from 'node:fs';
const BASE = process.env.E2E_BASE, OUT = process.env.OUT, PHASE = process.env.PHASE, AXE = process.env.AXE;
const { chromium } = createRequire('/opt/node22/lib/node_modules/')('playwright');
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const issues = [], consoleErr = [], csp = [], axeAll = [], res = [];
await ctx.addInitScript(() => { window.__csp = []; document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI)); });
page.on('pageerror', (e) => consoleErr.push('pageerror: ' + e.message));
page.on('console', (m) => { if (m.type() === 'error' || /Content Security Policy/i.test(m.text())) consoleErr.push(`[${m.type()}] ` + m.text().slice(0, 250)); });
const cdp = await ctx.newCDPSession(page);
cdp.on('Audits.issueAdded', (e) => { const i = e.issue; issues.push(i.code + ' ' + JSON.stringify(i.details).slice(0, 400)); });
await cdp.send('Audits.enable');
const api = async (p) => { const r = await ctx.request.get(BASE + '/api/v1' + p); return r.json().catch(() => ({})); };
const log = (v, id, title, exp, act, shot) => { res.push({ id, title, exp, act, v, shot }); console.log(v, id, title, '->', act); };
async function judge(id, title, exp, fn, h = 1000) {
  let v = 'PASS', act = '';
  try { act = (await fn()) || ''; } catch (e) { v = 'FAIL'; act = String(e.message).split('\n')[0]; }
  const shot = `${PHASE}-${id}.png`;
  try { await page.setViewportSize({ width: 1280, height: h }); await page.waitForTimeout(400); await page.screenshot({ path: `${OUT}/${shot}`, fullPage: true }); } catch { }
  log(v, id, title, exp, act, shot);
}
const need = (c, m) => { if (!c) throw new Error(m); };
const txt = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ');
async function axeRun(name) {
  try {
    await page.evaluate(fs.readFileSync(AXE, 'utf8'));
    const r = await page.evaluate(async () => { const x = await window.axe.run(document, { resultTypes: ['violations'] }); return x.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, n: v.nodes.length, el: v.nodes.slice(0, 3).map((n) => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\n')[1]) })); });
    axeAll.push({ screen: name, v: r });
  } catch (e) { axeAll.push({ screen: name, err: String(e.message).slice(0, 200) }); }
}
async function go(h, ready) { await page.goto(`${BASE}/#${h}`); if (ready) await page.getByText(ready).first().waitFor({ timeout: 20000 }); await page.waitForTimeout(800); }
async function tabTo(test, max = 250) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab');
    const info = await page.evaluate(() => { const e = document.activeElement; if (!e) return {}; const t = (e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].innerText) || e.innerText || e.placeholder || '').trim().replace(/\s+/g, ' '); return { tag: e.tagName, type: e.type, t, row: (e.closest('tr') || {}).innerText || '', art: (e.closest('article') || {}).innerText || '', dis: e.disabled }; });
    if (test(info)) return info;
  }
  throw new Error('Tab 으로 도달 못함(' + max + '회)');
}
const footer = async () => { const t = await txt(); return t.includes('면책 및 AI 안내') || t.includes('법률 자문이 아니며'); };

if (PHASE === 'empty') {
  await judge('S01', '홈(영상 없음) 안내', '"아직 영상이 없습니다. 데모 영상 200개를 불러와 시작하세요." + [데모 영상 불러오기] 버튼', async () => {
    await go('/', '홈'); const t = await txt();
    need(t.includes('아직 영상이 없습니다. 데모 영상 200개를 불러와 시작하세요.'), '홈 안내 문구 없음');
    need(await page.getByRole('button', { name: '데모 영상 불러오기' }).count() > 0, '[데모 영상 불러오기] 버튼 없음');
    return '문구와 버튼 확인';
  });
  await axeRun('홈(빈)');
  await judge('S02', '영상 목록 빈 화면', '"아직 영상이 없습니다" + "홈에서 \"데모 영상 불러오기\"를 눌러 연습용 영상 200개를 만들 수 있습니다."', async () => {
    await go('/videos'); await page.waitForTimeout(1200); const t = await txt();
    need(t.includes('아직 영상이 없습니다'), '빈 화면 제목 없음'); need(t.includes('데모 영상 불러오기'), '빈 화면 본문 안내 없음');
    return '제목·본문 확인';
  });
  await axeRun('영상 목록(빈)');
  await judge('S03', '푸터 면책·AI 고지(홈)', '"면책 및 AI 안내" 또는 법률 자문 아님 문구가 화면에 있음', async () => { await go('/', '홈'); need(await footer(), '푸터 면책 문구 없음'); const t = await txt(); need(t.includes('AI가 생성한 제안입니다'), 'AI 고지 없음(홈)'); return '푸터에 면책+AI 고지 확인(건강·금융 주의는 영상 상세·배치 상세에 있음)'; });
}
if (PHASE === 'full') {
  await go('/', '홈');
  const vids = (await api('/videos?page_size=20')).items || [];
  const ok = vids.filter((v) => !v.excluded && !(v.exclusion_reasons || []).length);
  const V = process.env.VID || (ok[5] || vids[5]).video_id;
  await go(`/videos/${V}`, 'AI 제안 만들기');
  await judge('S10', '영상 상세→AI 제안 만들기→카드의 제안 종류 표시', '카드에 "연습용 모의 제안(데모)" 표시', async () => {
    await page.getByRole('button', { name: 'AI 제안 만들기' }).first().click();
    for (let i = 0; i < 40; i++) { if (((await api(`/suggestions?video_id=${V}`)).items || []).length >= 2) break; await page.waitForTimeout(1000); }
    await page.reload(); await page.getByText('변경 전/후 비교').first().waitFor({ timeout: 15000 });
    need((await txt()).includes('연습용 모의 제안(데모)'), '제안 종류 문구 없음'); return '표시 확인';
  }, 2400);
  await judge('S11', '영상 상세의 면책·AI 고지·건강금융 주의', '"법률 자문이 아니며 최종 책임은 채널 소유자", "AI가 생성한 제안", "건강·금융" 주의', async () => {
    const t = await txt(); need(t.includes('법률 자문이 아니며 최종 책임은 채널 소유자'), '면책 없음'); need(t.includes('AI가 생성한 제안'), 'AI 고지 없음');
    need(t.includes('AI 제안은 사실과 법령 적합성을 보장하지 않습니다. 건강·금융 내용은'), 'AI 한계/건강·금융 주의 없음'); need(await footer(), '푸터 없음'); return '모두 확인';
  }, 2400);
  await axeRun('영상 상세');
  await go('/videos', '영상 목록'); await page.locator('tbody tr').first().waitFor();
  await judge('S12', '영상 목록(데이터 있음)', '표 행 존재, 푸터 면책', async () => { need((await page.locator('tbody tr').count()) > 0, '행 없음'); need(await footer(), '푸터 없음'); return (await page.locator('tbody tr').count()) + '행'; });
  await axeRun('영상 목록');
  await go('/', '홈');
  await judge('S13', '홈(영상·제안 있음) 안내와 오늘 할 일', '"오늘 할 일" 에 검토할 AI 제안 안내, 면책 푸터', async () => { const t = await txt(); need(t.includes('오늘 할 일'), '오늘 할 일 없음'); need(/검토할 AI 제안이 \d+개 영상에 있습니다|승인된 제안/.test(t), '제안 검토 안내 없음'); need(await footer(), '푸터 없음'); return '확인'; });
  await axeRun('홈');
  // ---- 키보드 전용 흐름 ----
  const kb = [];
  const step = async (n, f) => { try { const r = await f(); kb.push(['PASS', n, r || '']); } catch (e) { kb.push(['FAIL', n, String(e.message).split('\n')[0]]); throw e; } };
  let sug;
  try {
    await go(`/videos/${V}`, '변경 전/후 비교');
    sug = ((await api(`/suggestions?video_id=${V}`)).items || []).find((s) => s.validation_result !== 'block' && s.status !== 'approved');
    await page.evaluate(() => { window.scrollTo(0, 0); document.activeElement && document.activeElement.blur(); });
    await step('K1 Tab 으로 제안 카드 [승인] 버튼 도달', async () => { const i = await tabTo((x) => x.tag === 'BUTTON' && x.t === '승인' && x.art.includes(sug.title)); return 'text=' + i.t; });
    await step('K2 Enter 로 승인 창 열림', async () => { await page.keyboard.press('Enter'); await page.getByRole('dialog').waitFor({ timeout: 5000 }); });
    await step('K3 Tab 으로 승인자 이름 입력칸 도달 후 입력', async () => { await tabTo((x) => x.tag === 'INPUT' && /승인자/.test(x.t)); await page.keyboard.type('키보드시험'); });
    if (await page.getByLabel(/경고 사유를 모두 읽고/).count()) await step('K3b Space 로 경고 확인란 선택', async () => { await tabTo((x) => x.type === 'checkbox'); await page.keyboard.press('Space'); });
    await step('K4 Tab 으로 창 안 [승인] 버튼 도달 후 Enter', async () => { await tabTo((x) => x.tag === 'BUTTON' && x.t === '승인' && !x.art.includes('변경 전/후')); await page.keyboard.press('Enter'); await page.getByText('승인했습니다.').first().waitFor({ timeout: 10000 }); });
    await go('/batches', '반영할 승인 항목 고르기'); await page.locator('tbody tr', { hasText: V }).first().waitFor({ timeout: 15000 });
    await page.evaluate(() => { window.scrollTo(0, 0); document.activeElement && document.activeElement.blur(); });
    await step('K5 Tab+Space 로 승인 항목 선택', async () => { await tabTo((x) => x.type === 'checkbox' && x.row.includes(V)); await page.keyboard.press('Space'); });
    await step('K6 Tab+Enter 로 [사전 점검 만들기]', async () => { await tabTo((x) => x.tag === 'BUTTON' && x.t === '사전 점검 만들기'); await page.keyboard.press('Enter'); await page.getByText('사전 점검(미리보기)').waitFor({ timeout: 20000 }); });
    await step('K7 Tab 으로 확인 문구 입력', async () => { await tabTo((x) => x.tag === 'INPUT' && /확인 문구/.test(x.t)); await page.keyboard.type('실행 1건'); });
    await judge('S20', '배치 상세 [실행] 버튼 아래 "아직 필요한 것" (A/B 미확인)', '버튼 비활성 + "아직 필요한 것" + A/B 항목 안내(문구는 입력했으므로 확인 문구 항목은 없음)', async () => {
      const t = await txt(); need(t.includes('아직 필요한 것'), '"아직 필요한 것" 안내 없음'); need(t.includes('A/B 테스트 확인: 위의 확인란을 선택하세요.'), 'A/B 안내 없음');
      need(await page.getByRole('button', { name: '실행', exact: true }).isDisabled(), '실행 버튼이 켜져 있음'); return '안내 표시·버튼 비활성'; }, 2000);
    await axeRun('배치 상세(실행 전)');
    await step('K8 Tab+Space 로 A/B 확인란 선택', async () => { await tabTo((x) => x.type === 'checkbox' && /A\/B/.test(x.t)); await page.keyboard.press('Space'); });
    await judge('S21', '조건 충족 후 안내', '"필요한 조건을 모두 채웠습니다" 표시 + 실행 활성', async () => { const t = await txt(); need(t.includes('필요한 조건을 모두 채웠습니다'), '완료 안내 없음'); need(!(await page.getByRole('button', { name: '실행', exact: true }).isDisabled()), '실행 비활성'); need(t.includes('AI 제안은 사실과 법령 적합성을 보장하지 않습니다'), 'AI 한계 문구 없음(배치)'); return '확인'; }, 2000);
    await step('K9 Tab+Enter 로 [실행]', async () => { await tabTo((x) => x.tag === 'BUTTON' && x.t === '실행'); await page.keyboard.press('Enter'); await page.getByText('이 배치는 끝났습니다').waitFor({ timeout: 60000 }); });
  } catch { }
  fs.writeFileSync(`${OUT}/keyboard.json`, JSON.stringify(kb, null, 1));
  await go('/batches', '배치'); await axeRun('배치 목록');
  const b = ((await api('/batches')).items || [])[0];
  if (b) { await go(`/batches/${b.id}`); await page.waitForTimeout(1000); await axeRun('배치 상세(완료)'); }
  await go('/history', '이력'); await judge('S30', '이력 화면', '이력 표와 AI 고지', async () => { need((await txt()).includes('AI가 생성한 제안'), 'AI 고지 없음'); return '확인'; }); await axeRun('이력·롤백');
  await go('/reports', '성과'); await judge('S31', '리포트 화면', '면책 문구', async () => { need((await txt()).includes('법률 자문이 아니며'), '면책 없음'); return '확인'; }); await axeRun('성과 리포트');
  await go('/settings', '설정'); await axeRun('설정');
}
const u = [...new Set(await page.evaluate(() => window.__csp || []).catch(() => []))];
fs.writeFileSync(`${OUT}/${PHASE}-result.json`, JSON.stringify({ res, issues, consoleErr, csp: u, axe: axeAll }, null, 1));
console.log('issues', issues.length, 'console', consoleErr.length, 'csp', u.length);
await browser.close();
