// f: TC-E08/E20 단독 재실행. 소스 수정 없음. 사용: E2E_BASE=http://127.0.0.1:18080 OUT=<폴더> node rerun_e08_e20.mjs
// 전제: 데모 스택이 떠 있고 영상이 로드됨(없으면 홈의 [데모 영상 불러오기]). 원래 e2e_functional.mjs 의 TC-E08/E20 은 수정하지 않았다.
import { createRequire } from 'node:module';
import fs from 'node:fs';
const BASE = process.env.E2E_BASE, OUT = process.env.OUT;
const { chromium } = createRequire('/opt/node22/lib/node_modules/')('playwright');
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const out = [];
const rec = (v, id, m) => { out.push({ v, id, m }); console.log(v, id, m); };
const api = async (p) => (await (await ctx.request.get(BASE + '/api/v1' + p)).json().catch(() => ({})));
// ---- E08: 화면에서 수정한 바로 그 제안의 id 를 저장 요청에서 얻어 서버 상태를 확인
try {
  await page.goto(`${BASE}/#/`);
  const vids = (await api('/videos')).items || [];
  const V = (vids.find((v) => !v.excluded && !v.exclude_reason) || vids[0]).id ?? vids[0].video_id;
  await page.goto(`${BASE}/#/videos/${V}`);
  await page.getByText('변경 전/후 비교').first().waitFor({ timeout: 15000 }).catch(() => {});
  if (!(await page.getByRole('article').count())) { await page.getByRole('button', { name: 'AI 제안 만들기' }).first().click(); await page.getByText('변경 전/후 비교').first().waitFor({ timeout: 40000 }); }
  const card = page.getByRole('article').filter({ hasText: '변경 전/후' }).last();
  await card.getByRole('button', { name: '제목 수정' }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByLabel('새 제목').fill('이 영양제로 암 완치 가능합니다');
  const reqP = page.waitForRequest((r) => r.method() !== 'GET' && /\/suggestions\/\d+/.test(r.url()));
  await page.getByRole('dialog').getByRole('button', { name: /저장/ }).click();
  const sid = Number((await reqP).url().match(/\/suggestions\/(\d+)/)[1]);
  await page.getByText('제목을 수정했습니다').first().waitFor({ timeout: 10000 });
  const s = ((await api(`/suggestions?video_id=${V}`)).items || []).find((x) => x.id === sid);
  rec(s && s.validation_result === 'block' ? 'PASS' : 'FAIL', 'E08-server', `제안 ${sid} 검증결과=${s && s.validation_result} 제목=${s && s.title}`);
  const blocked = page.getByRole('article').filter({ hasText: '암 완치 가능합니다' }).last();
  rec(await blocked.getByRole('button', { name: '승인', exact: true }).isDisabled() ? 'PASS' : 'FAIL', 'E08-ui-disabled', '화면 [승인] 비활성');
  rec((await blocked.getByText('승인할 수 없는 이유').count()) > 0 ? 'PASS' : 'FAIL', 'E08-ui-reason', '"승인할 수 없는 이유" 표시');
  const csrf = (await api('/auth/me')).csrf_token;
  const r = await ctx.request.post(`${BASE}/api/v1/suggestions/${sid}/approve`, { data: { approver: '시험자' }, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, Origin: BASE } });
  rec(r.status() >= 400 ? 'PASS' : 'FAIL', 'E08-approve-refused', `승인 요청 ${r.status()}`);
  await page.screenshot({ path: `${OUT}/f-E08.png` });
} catch (e) { rec('FAIL', 'E08', String(e.message).split('\n')[0]); }
// ---- E20: 보안. 잘못된 Host 는 nginx 설계상 444(응답 없이 연결 종료)이므로 'HTTP 4xx 또는 연결 종료'를 모두 거부로 인정(근거: docs/yt/API.md:23, threat_model TW-02)
try {
  const anon = await browser.newContext();
  const r1 = await anon.request.get(`${BASE}/api/v1/videos`); rec(r1.status() === 401 ? 'PASS' : 'FAIL', 'E20-anon', `세션 없는 조회 ${r1.status()}`);
  let hostRes; try { const r = await anon.request.get(`${BASE}/api/v1/auth/me`, { headers: { Host: 'evil.example' }, maxRedirects: 0 }); hostRes = r.status() >= 400 ? `HTTP ${r.status()}` : null; if (!hostRes) hostRes = 'FAIL ' + r.status(); } catch (e) { hostRes = /socket hang up|ECONNRESET/.test(e.message) ? 'conn-closed(444)' : 'FAIL ' + e.message; }
  rec(hostRes.startsWith('FAIL') ? 'FAIL' : 'PASS', 'E20-badhost', hostRes);
  for (const p of ['/docs', '/openapi.json', '/api/docs', '/api/openapi.json', '/redoc']) { const r = await anon.request.get(BASE + p); const t = await r.text(); rec(/swagger|openapi"?\s*:|redoc/i.test(t) ? 'FAIL' : 'PASS', 'E20-docs' + p, `${r.status()} ${r.headers()['content-type']}`); }
  const r4 = await anon.request.post(`${BASE}/api/v1/batches/999/cancel`, { headers: { Origin: BASE } }); rec(r4.status() >= 400 ? 'PASS' : 'FAIL', 'E20-csrf-anon', `${r4.status()}`);
  const r5 = await ctx.request.post(`${BASE}/api/v1/batches/999/cancel`, { headers: { Origin: BASE } }); rec(r5.status() === 403 || r5.status() === 401 ? 'PASS' : 'FAIL', 'E20-csrf-no-token', `세션 있음·토큰 없음 ${r5.status()}`);
  const r6 = await ctx.request.post(`${BASE}/api/v1/batches/999/cancel`, { headers: { Origin: 'http://evil.example', 'X-CSRF-Token': (await api('/auth/me')).csrf_token } }); rec(r6.status() >= 400 ? 'PASS' : 'FAIL', 'E20-bad-origin', `${r6.status()}`);
  await anon.close();
} catch (e) { rec('FAIL', 'E20', String(e.message).split('\n')[0]); }
fs.writeFileSync(`${OUT}/f-result.json`, JSON.stringify(out, null, 2));
await browser.close();
process.exit(out.some((o) => o.v === 'FAIL') ? 1 : 0);
