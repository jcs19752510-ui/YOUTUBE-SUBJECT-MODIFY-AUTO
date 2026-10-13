// 일괄 승인 화면 자동 실행·캡처(vite 개발 서버 + API 목). 사용: node capture_bulk.mjs <BASE_URL> <OUT_DIR>
import { createRequire } from 'node:module';
import fs from 'node:fs';
const { chromium } = createRequire('/opt/node22/lib/node_modules/')('playwright');
const [BASE, OUT] = process.argv.slice(2);
const V = (n) => `vid${String(n).padStart(8, '0')}`;
const sg = (id, vid, title, vr = 'pass', st = 'candidate') => ({
  id, video_id: vid, title, evidence: 'e', source: 'ai:mock', topic: '생활', strict: false,
  validation_result: vr, reasons: [], length: title.length, match_ratio: 0.9, status: st, plan_hash: null,
  approval: null, created_at: '2026-10-10T00:00:00Z',
});
const A = [sg(1, V(1), '무릎 아플 때 좋은 운동 3가지'), sg(2, V(2), '혈압 낮추는 아침 습관 지금 시작하세요 꼭 알아야 할 것', 'warn'),
  sg(3, V(3), '겨울철 낙상 예방 방법'), sg(4, V(4), '무조건 낫는 비법 공개', 'block', 'blocked')];
const cur = { [V(1)]: '무릎 운동 영상', [V(2)]: '혈압 관리 팁', [V(3)]: '낙상 예방', [V(4)]: '건강 비법', [V(5)]: '시니어 걷기 운동', [V(6)]: '수면 습관' };
const B5 = [sg(51, V(5), '걷기 운동 하루 30분 효과'), sg(52, V(5), '시니어 걷기 이렇게 하세요')];
const B6 = [sg(61, V(6), '숙면에 좋은 저녁 습관')];
const resolve = (ids) => ids.map((v) => ({ video_id: v, found: v in cur, video_title: cur[v] ?? null, excluded_reasons: [],
  candidates: v === V(5) ? B5 : v === V(6) ? B6 : A.filter((s) => s.video_id === v) }));
const rows = [];
const log = [];
const b = await chromium.launch();
const page = await (await b.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
page.on('pageerror', (e) => log.push('PAGEERROR ' + e.message));
let approveBody = null;
await page.route('**/api/v1/**', async (r) => {
  const u = new URL(r.request().url()); const m = r.request().method();
  const j = (o, s = 200) => r.fulfill({ status: s, contentType: 'application/json', body: JSON.stringify(o) });
  if (u.pathname.endsWith('/auth/me')) return j({ authenticated: true, pin_required: false, csrf_token: 'c' });
  if (u.pathname.endsWith('/suggestions/resolve-videos')) return j({ items: resolve(r.request().postDataJSON().video_ids) });
  if (u.pathname.endsWith('/suggestions/approve-batch')) {
    approveBody = r.request().postDataJSON();
    return j({ approved: [1, 2, 51].map((i) => ({ suggestion_id: i, video_id: i === 51 ? V(5) : V(i) })),
      skipped: [{ suggestion_id: 61, video_id: V(6), code: 'suggestion_state', reason: 'x' }], counts: { requested: 4, approved: 3, skipped: 1 } });
  }
  if (u.pathname.endsWith('/suggestions') && m === 'GET')
    return j({ items: u.searchParams.get('status') === 'expired' ? [] : A, total: 4, page: 1, page_size: 50 });
  log.push('UNHANDLED ' + m + ' ' + u.pathname);
  return j({ detail: 'unhandled' }, 404);
});
const txt = async () => (await page.locator('body').innerText());
const check = async (id, name, expect, fn) => {
  let ok = false, actual = '';
  try { [ok, actual] = await fn(); } catch (e) { actual = 'ERR ' + String(e.message).split('\n')[0]; }
  if (id.startsWith('05') || id.startsWith('06')) await page.getByRole('dialog').getByRole('button', { name: /건 승인$/ }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${OUT}/${id}.png` });
  rows.push({ id, name, expect, actual, ok });
};
await page.goto(`${BASE}/#/bulk-approve`);
await page.getByRole('heading', { name: '일괄 승인', exact: true }).waitFor({ timeout: 15000 }).catch(async () => { console.log((await page.locator('body').innerText()).slice(0, 300)); throw new Error('heading'); });
await page.getByText('무릎 운동 영상').first().waitFor();
await check('01-initial', '초기', '제목 일괄 승인 화면, 방법 A 표에 현재 제목과 새 제목 4행, 선택 0/50건', async () => {
  const t = await txt(); const ok = t.includes('무릎 운동 영상') && t.includes('무릎 아플 때 좋은 운동 3가지') && t.includes('선택 0/50건');
  return [ok, `현재 제목 보임=${t.includes('무릎 운동 영상')}, 선택 0/50건=${t.includes('선택 0/50건')}`];
});
for (const n of [1, 2, 3]) await page.getByRole('checkbox', { name: new RegExp(`${A[n - 1].title.slice(0, 8)}.* 선택$`) }).check();
await check('02-methodA', '방법 A 선택', '체크 3건 활성, 차단 1건 체크박스 비활성, 선택 3/50건, 차단 사유 글', async () => {
  const dis = await page.getByRole('checkbox', { name: new RegExp(A[3].title.slice(0, 8)) }).first().isDisabled();
  const t = await txt(); return [dis && t.includes('선택 3/50건') && t.includes('차단 판정이라 승인할 수 없습니다'), `차단 비활성=${dis}, 선택 3/50건=${t.includes('선택 3/50건')}`];
});
await page.getByRole('textbox', { name: /영상 ID/ }).fill(`${V(5)}\n${V(6)}`);
await page.getByRole('button', { name: '찾기' }).click();
await page.getByText('찾은 결과 2개 영상').waitFor();
await check('03-methodB-need-choice', '방법 B 붙여넣기', '영상 5 는 후보 2개라 "후보 선택 필요" 글, 영상 6 은 후보 1개 자동 선택, 선택 4/50건', async () => {
  const t = await txt(); return [/선택/.test(t) && t.includes('시니어 걷기 운동') && t.includes('선택 4/50건'), `선택 4/50건=${t.includes('선택 4/50건')}, 후보 선택 안내 글=${/후보.*선택/.test(t)}`];
});
await page.getByRole('radio', { name: /걷기 운동 하루 30분 효과/ }).check();
await check('04-queue', '라디오 선택 후 승인 대기 목록', '대기 목록 5건(영상 1·2·3·5·6, 현재 제목→새 제목), 선택 5/50건', async () => {
  const t = await txt(); return [t.includes('선택 5/50건') && t.includes('걷기 운동 하루 30분 효과'), `선택 5/50건=${t.includes('선택 5/50건')}`];
});
await page.getByRole('button', { name: '확인 창 열기' }).click();
const dlg = page.getByRole('dialog');
await dlg.getByRole('textbox', { name: /승인자 이름/ }).fill('선생님');
await check('05-dialog-blocked', '확인 창, 경고 체크 전', '현재 제목 표시, 승인 버튼 비활성, 남은 조건 글(경고 1건 확인)', async () => {
  const dis = await dlg.getByRole('button', { name: /건 승인$/ }).isDisabled(); const t = await dlg.innerText();
  return [dis && t.includes('경고가 있는 1건') && t.includes('혈압 관리 팁'), `버튼 비활성=${dis}, 남은 조건 글=${t.includes('경고가 있는 1건')}, 현재 제목=${t.includes('혈압 관리 팁')}`];
});
await dlg.getByRole('checkbox', { name: /경고를 확인했습니다/ }).check();
await check('06-dialog-enabled', '경고 체크 후', '승인 버튼 활성, 남은 조건 글 사라짐', async () => {
  const en = await dlg.getByRole('button', { name: /건 승인$/ }).isEnabled(); const t = await dlg.innerText();
  return [en && !t.includes('경고가 있는 1건'), `버튼 활성=${en}`];
});
await dlg.getByRole('button', { name: /건 승인$/ }).click();
await page.getByText(/승인 3건 \/ 제외 1건/).waitFor();
await check('07-result', '결과 패널', '승인 3건 / 제외 1건, 제외 사유 글, 제목은 바뀌지 않음 문구, 요청에 경고확인 ID 2 포함', async () => {
  const t = await txt(); const ack = JSON.stringify(approveBody?.acknowledged_warning_ids);
  return [t.includes('승인 3건 / 제외 1건') && t.includes('승인할 수 있는 상태가 아닙니다') && ack === '[2]', `요약=${t.includes('승인 3건 / 제외 1건')}, 사유=${t.includes('승인할 수 있는 상태가 아닙니다')}, 보낸 경고확인=${ack}, 보낸 ID=${JSON.stringify(approveBody?.suggestion_ids)}`];
});
await b.close();
fs.writeFileSync(`${OUT}/rows.json`, JSON.stringify({ rows, log }, null, 1));
console.log(rows.map((r) => `${r.ok ? 'PASS' : 'FAIL'} ${r.id} ${r.actual}`).join('\n'), '\n', log.join('\n'));
