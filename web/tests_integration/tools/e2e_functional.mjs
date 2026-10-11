// 기능 자동 시험(E2E): 실제 브라우저로 화면을 조작하고, 단계마다 "예상 결과"와 "실제 결과"를 비교해 합격/불합격을 기록하며 화면을 캡처한다.
// 대상: 이미 떠 있는 서버(기본 http://127.0.0.1:8080, 데모 모드). 실제 유튜브·AI 는 호출하지 않는다.
// 환경변수: E2E_BASE, E2E_OUT, PW_PATH(playwright 가 설치된 node_modules 폴더, 끝에 / 포함), E2E_CHANNEL(msedge|chrome, 설치된 브라우저 사용)
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const BASE = process.env.E2E_BASE || 'http://127.0.0.1:8080';
const OUT = process.env.E2E_OUT || path.resolve('e2e-out');
const PW = process.env.PW_PATH || '/opt/node22/lib/node_modules/';
const CHANNEL = process.env.E2E_CHANNEL || '';
const { chromium } = createRequire(PW)('playwright');
fs.mkdirSync(OUT, { recursive: true });

const results = [];
const browser = await chromium.launch(CHANNEL ? { channel: CHANNEL } : {});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const consoleErrors = [];
page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });

const api = async (p) => {
  const r = await ctx.request.get(BASE + '/api/v1' + p);
  const ct = r.headers()['content-type'] || '';
  return { status: r.status(), ct, body: ct.includes('json') ? await r.json() : await r.text() };
};
function eq(actual, expected, what) { if (actual !== expected) throw new Error(`${what}: 예상 ${JSON.stringify(expected)} / 실제 ${JSON.stringify(actual)}`); }
function ok(cond, msg) { if (!cond) throw new Error(msg); }
async function shot(id, h = 900) { await page.setViewportSize({ width: 1280, height: h }); await page.waitForTimeout(500); await page.screenshot({ path: `${OUT}/${id}.png` }); }
async function tc(id, title, expected, fn, h = 900) {
  const rec = { id, title, expected, actual: '', verdict: 'Pass', shot: `${id}.png` };
  try { rec.actual = (await fn()) || '예상과 일치'; }
  catch (e) { rec.verdict = 'Fail'; rec.actual = String(e.message).split('\n')[0]; }
  try { await shot(id, h); } catch { rec.shot = ''; }
  results.push(rec);
  console.log(`${rec.verdict.padEnd(4)} ${id} ${title} -> ${rec.actual}`);
}

let V = null, vOrig = '', vNew = '', sugIds = [];

await tc('TC-E01', '홈 화면이 열리고 데모 모드·서버 연결 표시가 보인다', '"데모 모드" 배지, "서버 연결됨", 제목 "홈"', async () => {
  await page.goto(`${BASE}/#/`);
  await page.getByRole('heading', { name: '홈', exact: true }).waitFor({ timeout: 20000 });
  await page.getByText('데모 모드 —').first().waitFor();
  await page.getByText('서버 연결됨').first().waitFor();
  const live = await page.getByText('실제 반영(라이브): 꺼짐').count();
  ok(live > 0, '"실제 반영(라이브): 꺼짐" 표시가 없음');
  return '데모 배지·서버 연결됨·라이브 꺼짐 확인';
});

await tc('TC-E02', '데모 영상 200개가 준비된다(비어 있으면 [데모 영상 불러오기]로 채움)', '전체 영상 200개', async () => {
  const btn = page.getByRole('button', { name: '데모 영상 불러오기' });
  if (await btn.count()) { await btn.click(); await page.waitForTimeout(500); }
  let n = 0;
  for (let i = 0; i < 40; i++) { n = (await api('/dashboard')).body.counts?.videos ?? 0; if (n === 200) break; await page.waitForTimeout(1000); }
  eq(n, 200, '전체 영상 수');
  await page.goto(`${BASE}/#/`); await page.waitForTimeout(1500);
  return '전체 영상 200개';
});

await tc('TC-E03', '영상 목록: 검색이 동작하고 결과가 줄어든다', '"냉장고" 검색 → 모든 행 제목에 "냉장고" 포함, 200개보다 적음', async () => {
  await page.goto(`${BASE}/#/videos`); await page.getByRole('table').waitFor();
  await page.locator('tbody tr').first().waitFor();
  const box = page.getByPlaceholder(/전기요금|검색/).first();
  await box.fill('냉장고'); await page.getByRole('button', { name: '검색' }).click();
  await page.waitForTimeout(1500);
  const rows = await page.locator('tbody tr').allInnerTexts();
  ok(rows.length > 0 && rows.length < 200, `검색 결과 행 수 ${rows.length}`);
  ok(rows.every((r) => r.includes('냉장고')), '검색 결과에 "냉장고"가 없는 행이 있음');
  return `검색 결과 ${rows.length}행, 모두 "냉장고" 포함`;
});

await tc('TC-E04', '제외 대상 영상(쇼츠·비공개 등)은 선택할 수 없다', '제외 배지가 있는 행의 체크박스가 비활성, 서버 제외 영상 37개', async () => {
  await page.goto(`${BASE}/#/videos`); await page.getByRole('table').waitFor();
  const ex = await api('/videos?excluded=true&page_size=200');
  eq(ex.body.total, 37, '제외된 영상 수');
  const row = page.locator('tbody tr', { hasText: '제외' }).first();
  await row.waitFor({ timeout: 10000 });
  const disabled = await row.locator('input[type=checkbox]').isDisabled();
  eq(disabled, true, '제외 영상 체크박스 비활성');
  return '제외 영상 37개, 체크박스 비활성 확인';
});

// 시험 대상 영상 고르기: 제외되지 않고 제안/변경 이력이 없는 첫 영상
{
  const list = await api('/videos?excluded=false&page_size=200');
  const cand = (list.body.items || []).find((v) => v.workflow_status === 'none' && !v.excluded);
  if (cand) { V = cand.video_id; vOrig = cand.title; }
}

await tc('TC-E05', '영상 상세가 열리고 현재 제목이 서버 값과 같다', '영상 상세 제목 = 서버의 제목', async () => {
  ok(V, '시험할 수 있는 영상(제안 없음, 제외 아님)이 없음');
  await page.goto(`${BASE}/#/videos/${V}`);
  await page.getByRole('heading', { name: '영상 상세' }).waitFor();
  await page.getByText(vOrig).first().waitFor({ timeout: 15000 });
  return `${V} "${vOrig}"`;
});

await tc('TC-E06', 'AI 제안 만들기: 제안이 2건 이상 생기고 검증 결과가 붙는다', '제안 2건 이상, 각 제안의 검증 결과가 pass/warn/block 중 하나', async () => {
  await page.getByRole('button', { name: 'AI 제안 만들기' }).first().click();
  let items = [];
  for (let i = 0; i < 40; i++) { items = (await api(`/suggestions?video_id=${V}`)).body.items || []; if (items.length >= 2) break; await page.waitForTimeout(1000); }
  ok(items.length >= 2, `제안 수 ${items.length}`);
  ok(items.every((s) => ['pass', 'warn', 'block'].includes(s.validation_result)), '검증 결과 값이 올바르지 않음');
  sugIds = items.map((s) => s.id);
  await page.reload(); await page.getByText('변경 전/후 비교').first().waitFor({ timeout: 15000 });
  return `제안 ${items.length}건: ` + items.map((s) => s.validation_result).join(', ');
}, 2300);

await tc('TC-E07', '면책·AI 생성 고지 문구가 상세 화면에 보인다', '"법률 자문이 아니며 최종 책임은 채널 소유자" 및 "AI가 생성한 제안" 문구', async () => {
  const t = await page.locator('body').innerText();
  ok(t.includes('법률 자문이 아니며 최종 책임은 채널 소유자'), '면책 문구 없음');
  ok(t.includes('AI가 생성한 제안'), 'AI 생성 고지 없음');
  return '면책·AI 고지 문구 확인';
}, 2300);

await tc('TC-E08', '민감 문구("완치")를 넣은 제목은 "차단"되고 승인할 수 없다', '수정 후 검증 결과 block, 그 카드의 [승인] 버튼이 비활성이고 "승인할 수 없는 이유"가 보임, 서버도 승인 거부', async () => {
  const sid = sugIds[sugIds.length - 1];
  const card = page.getByRole('article').filter({ hasText: '변경 전/후' }).last();
  await card.getByRole('button', { name: '제목 수정' }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByLabel('새 제목').fill('이 영양제로 암 완치 가능합니다');
  await page.getByRole('dialog').getByRole('button', { name: /저장/ }).click();
  await page.getByText('제목을 수정했습니다').first().waitFor({ timeout: 10000 });
  const s = (await api(`/suggestions?video_id=${V}`)).body.items.find((x) => x.id === sid);
  eq(s.validation_result, 'block', '수정 후 검증 결과');
  await page.waitForTimeout(800);
  const blockedCard = page.getByRole('article').filter({ hasText: '암 완치 가능합니다' }).last();
  eq(await blockedCard.getByRole('button', { name: '승인', exact: true }).isDisabled(), true, '차단된 카드의 [승인] 버튼 비활성');
  ok((await blockedCard.getByText('승인할 수 없는 이유').count()) > 0, '"승인할 수 없는 이유" 안내가 없음');
  const r = await ctx.request.post(`${BASE}/api/v1/suggestions/${sid}/approve`, { data: { approver: '시험자' }, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': (await api('/auth/me')).body.csrf_token, Origin: BASE } });
  ok(r.status() >= 400, `서버가 차단 제안 승인을 거부해야 함(실제 ${r.status()})`);
  return `차단 판정, [승인] 버튼 비활성+"승인할 수 없는 이유" 안내 표시, 서버 승인 요청 거부(${r.status()})`;
}, 2300);

await tc('TC-E09', '승인: 승인자 이름이 비어 있으면 거부, 입력하면 "승인됨"이 된다', '빈 이름 → 승인 안 됨 + 사용자에게 이유 안내 문구가 보임 / 이름 입력 → 서버 상태 approved, 승인자 기록', async () => {
  const first = (await api(`/suggestions?video_id=${V}`)).body.items.find((s) => s.validation_result !== 'block' && s.status !== 'approved');
  ok(first, '승인할 수 있는 제안이 없음');
  const card = page.locator('article', { hasText: first.title }).first();
  await card.getByRole('button', { name: '승인', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  const name = page.getByLabel('승인자 이름'); await name.fill('');
  const ack = page.getByLabel(/경고 사유를 모두 읽고/); if (await ack.count()) await ack.check();
  const okBtn = page.getByRole('dialog').getByRole('button', { name: '승인', exact: true });
  // 사용자 관점: 이름이 비어 있으면 승인이 안 되는 것은 물론, "왜 안 되는지" 화면에 안내가 보여야 한다.
  const disabledNow = await okBtn.isDisabled();
  if (!disabledNow) await okBtn.click();
  await shot('TC-E09a');
  eq((await api(`/suggestions?video_id=${V}`)).body.items.find((s) => s.id === first.id).status !== 'approved', true, '빈 이름으로는 승인 안 됨');
  const hint = await page.getByRole('dialog').getByText('승인자 이름을 입력해 주세요').count();
  if (hint === 0) { await name.fill('시험자'); await okBtn.click({ timeout: 10000 }).catch(() => {}); throw new Error(`빈 이름일 때 [승인] 버튼이 ${disabledNow ? '비활성(회색)이지만' : '눌렸지만'} 이유 안내 문구("승인자 이름을 입력해 주세요")가 화면에 보이지 않음 — 사용자는 왜 안 되는지 알 수 없음`); }
  await name.fill('시험자');
  await okBtn.click();
  await page.getByText('승인했습니다.').first().waitFor({ timeout: 10000 });
  const s = (await api(`/suggestions?video_id=${V}`)).body.items.find((x) => x.id === first.id);
  eq(s.status, 'approved', '승인 후 상태'); eq(s.approval?.approver, '시험자', '승인자 기록');
  vNew = s.title;
  return `제안 ${s.id} 승인됨, 승인자 "시험자", 만료 ${s.approval.expires_at}`;
}, 2300);

await tc('TC-E10', '배치 사전 점검: 선택한 1건이 점검에 담기고 수치가 맞다', '반영 대상 1건, 예상 52단위, 서버 점검 결과와 화면 일치', async () => {
  await page.goto(`${BASE}/#/batches`); await page.getByText('반영할 승인 항목 고르기').waitFor();
  const row = page.locator('tbody tr', { hasText: V });
  await row.first().waitFor({ timeout: 15000 });
  await row.first().locator('input[type=checkbox]').check();
  await page.getByRole('button', { name: '사전 점검 만들기' }).click();
  await page.getByText('사전 점검(미리보기)').waitFor({ timeout: 20000 });
  const t = await page.locator('main').innerText();
  ok(/반영 대상\s*1건/.test(t.replace(/\n/g, ' ')), '"반영 대상 1건" 표시 없음');
  ok(t.includes('52 단위'), '"52 단위" 표시 없음');
  return '반영 대상 1건, 예상 52단위 표시';
}, 2000);

await tc('TC-E11', '실행 잠금: A/B 확인과 정확한 확인 문구가 있어야만 [실행]이 켜진다', '아무것도 안 하면 비활성 / 문구만 맞춰도 비활성 / A/B 확인+문구 일치 → 활성 / 문구 틀리면 비활성', async () => {
  const run = page.getByRole('button', { name: '실행', exact: true });
  eq(await run.isDisabled(), true, '초기 상태의 [실행] 비활성');
  const inp = page.getByLabel(/확인 문구/);
  await inp.fill('실행 1건');
  eq(await run.isDisabled(), true, 'A/B 확인 없이 문구만 맞춘 경우 비활성');
  const ab = page.getByLabel(/A\/B 테스트 중이 아님을 확인했습니다/); await ab.check();
  eq(await run.isDisabled(), false, 'A/B 확인+문구 일치 시 활성');
  await inp.fill('실행 2건');
  eq(await run.isDisabled(), true, '문구가 틀리면 다시 비활성');
  await inp.fill('실행 1건');
  eq(await run.isDisabled(), false, '문구 복구 후 활성');
  return '4가지 조합 모두 예상대로';
}, 2000);

await tc('TC-E12', '실행: 워커가 처리해 배치가 "완료·성공 1"이 된다', '배치 상태 done, 성공 1·실패 0, 화면 "이 배치는 끝났습니다"', async () => {
  await page.getByRole('button', { name: '실행', exact: true }).click();
  await page.getByText('이 배치는 끝났습니다').waitFor({ timeout: 60000 });
  const b = (await api('/batches')).body.items[0];
  eq(b.status, 'done', '배치 상태'); eq(b.counts.success, 1, '성공 건수'); eq(b.counts.failed, 0, '실패 건수');
  return `배치 #${b.id} done, 성공 ${b.counts.success}`;
});

await tc('TC-E13', '반영 결과: 영상의 현재 제목이 실제로 새 제목으로 바뀐다(데모 데이터)', '서버 영상 제목 = 승인한 새 제목, 상세 화면 현재 제목도 같음', async () => {
  if (!vNew) { const sg = (await api(`/suggestions?video_id=${V}`)).body.items.find((x) => ['applied', 'approved'].includes(x.status)); vNew = sg ? sg.title : ''; }
  const v = (await api(`/videos/${V}`)).body;
  eq(v.title, vNew, '서버의 영상 제목');
  ok(v.title !== vOrig, '제목이 그대로임');
  await page.goto(`${BASE}/#/videos/${V}`); await page.getByText(vNew).first().waitFor({ timeout: 15000 });
  return `"${vOrig}" → "${vNew}"`;
}, 1500);

await tc('TC-E14', '이력: 반영 기록 1건이 "성공"으로 남고 [롤백] 버튼이 있다', '이력에 해당 영상의 apply 성공 기록, 화면에 [롤백] 버튼', async () => {
  const ch = (await api(`/changes?video_id=${V}`)).body.items;
  ok(ch.some((c) => c.change_type === 'apply' && c.result === 'success'), '서버 이력에 반영 성공 기록 없음');
  await page.goto(`${BASE}/#/history`); await page.locator('main table').waitFor();
  await page.getByLabel('영상 ID로 찾기').fill(V); await page.getByRole('button', { name: '검색' }).click();
  await page.waitForTimeout(1200);
  const row = page.locator('tbody tr', { hasText: V }).first();
  await row.waitFor();
  eq(await row.getByRole('button', { name: '롤백' }).count(), 1, '[롤백] 버튼 수');
  return `이력 ${ch.length}건, 반영 성공 기록과 [롤백] 확인`;
});

await tc('TC-E15', '롤백 안전장치: 영상 ID를 틀리게 입력하면 [롤백 실행]이 꺼져 있다', '틀린 ID → 비활성, 올바른 ID+승인자 → 활성', async () => {
  const row = page.locator('tbody tr', { hasText: V }).first();
  await row.getByRole('button', { name: '롤백' }).click();
  await page.getByRole('dialog').waitFor();
  const submit = page.getByRole('dialog').getByRole('button', { name: '롤백 실행' });
  const dlg = page.getByRole('dialog'); await dlg.getByLabel(/영상 ID/).fill('wrongId');
  await dlg.getByLabel('승인자 이름').fill('시험자');
  eq(await submit.isDisabled(), true, '틀린 ID일 때 비활성');
  await dlg.getByLabel(/영상 ID/).fill(V);
  eq(await submit.isDisabled(), false, '올바른 ID일 때 활성');
  return '틀린 ID 비활성 / 올바른 ID 활성';
});

await tc('TC-E16', '롤백 실행: 제목이 원래대로 돌아오고 롤백 기록이 남는다', '서버 영상 제목 = 원래 제목, 이력에 rollback 성공 기록', async () => {
  await page.getByRole('dialog').getByRole('button', { name: '롤백 실행' }).click();
  await page.getByText('롤백했습니다.').first().waitFor({ timeout: 20000 });
  const v = (await api(`/videos/${V}`)).body;
  eq(v.title, vOrig, '롤백 후 영상 제목');
  const ch = (await api(`/changes?video_id=${V}`)).body.items;
  ok(ch.some((c) => c.change_type === 'rollback' && c.result === 'success'), '롤백 성공 기록 없음');
  return `제목 "${vOrig}"로 복원, 롤백 기록 확인`;
});

await tc('TC-E17', '성과 리포트: 안내 문구와 "데이터 부족"이 보이고 CSV가 내려온다', '"읽기 전에 꼭 확인하세요", "데이터 부족", CSV 응답 200', async () => {
  await page.goto(`${BASE}/#/reports`); await page.getByRole('heading', { name: '성과 리포트' }).waitFor();
  await page.getByText('읽기 전에 꼭 확인하세요').waitFor({ timeout: 10000 });
  ok((await page.getByText('데이터 부족').count()) > 0, '"데이터 부족" 표시 없음');
  const c = await ctx.request.get(`${BASE}/api/v1/reports/export.csv`);
  eq(c.status(), 200, 'CSV 응답 코드');
  ok((c.headers()['content-type'] || '').includes('csv'), 'CSV 형식이 아님');
  return 'CSV 200 응답, 안내 문구·데이터 부족 표시 확인';
});

await tc('TC-E18', '설정: 하루 반영 상한을 바꾸면 저장되고 홈에 반영된다(확인 후 원래 값 복구)', '상한 5로 저장 → 서버 값 5, 홈 "0 / 5건" → 원래 값으로 복구', async () => {
  const before = (await api('/settings')).body;
  const old = before.daily_apply_cap ?? before.settings?.daily_apply_cap;
  await page.goto(`${BASE}/#/settings`); await page.getByRole('heading', { name: '설정', exact: true }).waitFor();
  const cap = page.getByLabel('하루 반영 건수 상한');
  await cap.fill('5'); await page.getByRole('button', { name: '저장' }).click();
  await page.getByText('설정을 저장했습니다.').first().waitFor({ timeout: 10000 });
  const mid = (await api('/settings')).body; const nv = mid.daily_apply_cap ?? mid.settings?.daily_apply_cap;
  eq(nv, 5, '저장된 상한');
  await shot('TC-E18a');
  await page.goto(`${BASE}/#/`); await page.getByText(/\/ 5건/).first().waitFor({ timeout: 10000 });
  await page.goto(`${BASE}/#/settings`); await page.getByLabel('하루 반영 건수 상한').fill(String(old)); await page.getByRole('button', { name: '저장' }).click();
  await page.getByText('설정을 저장했습니다.').first().waitFor({ timeout: 10000 });
  const end = (await api('/settings')).body; eq(end.daily_apply_cap ?? end.settings?.daily_apply_cap, old, '복구된 상한');
  return `${old} → 5(홈 "0 / 5건" 확인) → ${old} 복구`;
});

await tc('TC-E19', '감사 로그: 기록이 쌓이고 변조 검사(체인)가 정상이다', '감사 로그 chain_ok = true, 기록 5건 이상', async () => {
  const a = (await api('/audit?page_size=200')).body;
  eq(a.chain_ok, true, 'chain_ok');
  ok((a.total ?? (a.items || []).length) >= 5, `기록 수 ${a.total}`);
  await page.goto(`${BASE}/#/settings`); await page.getByRole('tab', { name: '감사 로그' }).click();
  await page.waitForTimeout(1500);
  return `기록 ${a.total}건, 체인 정상`;
});

await tc('TC-E20', '보안: 로그인 없이는 API가 거부되고, 엉뚱한 주소로는 접근할 수 없다', '세션 없음 → 401, 잘못된 Host → 거부, 문서(/docs) 비공개, CSRF 없는 변경 요청 거부', async () => {
  const anon = await browser.newContext();
  const r1 = await anon.request.get(`${BASE}/api/v1/videos`);
  eq(r1.status(), 401, '세션 없는 조회');
  const r2 = await anon.request.get(`${BASE}/api/v1/auth/me`, { headers: { Host: 'evil.example' } });
  ok(r2.status() >= 400, `잘못된 Host 요청이 거부되어야 함(실제 ${r2.status()})`);
  const r3 = await anon.request.get(`${BASE}/docs`);
  ok(r3.status() === 404 || !(r3.headers()['content-type'] || '').includes('html') || !(await r3.text()).includes('swagger'), '/docs 가 공개됨');
  const r4 = await ctx.request.post(`${BASE}/api/v1/batches/999/cancel`, { headers: { Origin: BASE } });
  ok(r4.status() >= 400, `CSRF 없는 변경 요청이 거부되어야 함(실제 ${r4.status()})`);
  await anon.close();
  return `조회 401, 잘못된 Host ${r2.status()}, /docs ${r3.status()}(API 문서가 아니라 앱 첫 화면 index.html), CSRF 없는 변경 ${r4.status()}`;
});

await tc('TC-E21', '화면 오류: 시험 내내 브라우저 콘솔에 치명 오류가 없다', '페이지 오류(pageerror) 0건, CSP 위반 0건', async () => {
  const bad = consoleErrors.filter((e) => /pageerror|Content Security Policy|Refused to/.test(e));
  eq(bad.length, 0, '치명 오류 수');
  return `콘솔 오류 ${consoleErrors.length}건(치명 0건)`;
});

await browser.close();

const pass = results.filter((r) => r.verdict === 'Pass').length;
const summary = { base: BASE, when: new Date().toISOString(), total: results.length, pass, fail: results.length - pass, results, consoleErrors };
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(summary, null, 2));
let md = `# 기능 자동 시험 결과 (E2E)\n\n- 대상: ${BASE}\n- 실행: ${summary.when}\n- 결과: **${pass} / ${results.length} 통과**, 실패 ${summary.fail}\n\n| ID | 시나리오 | 예상 결과 | 실제 결과 | 판정 | 화면 |\n|---|---|---|---|---|---|\n`;
for (const r of results) md += `| ${r.id} | ${r.title} | ${r.expected} | ${r.actual.replace(/\|/g, '/')} | ${r.verdict} | ${r.shot ? `![${r.id}](${r.shot})` : '-'} |\n`;
fs.writeFileSync(`${OUT}/RESULT.md`, md);
console.log(`\n== ${pass}/${results.length} 통과 ==`);
process.exit(summary.fail ? 1 : 0);
