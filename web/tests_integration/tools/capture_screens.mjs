import { createRequire } from 'node:module';
import fs from 'node:fs';
const { chromium } = createRequire('/opt/node22/lib/node_modules/')('playwright');
const BASE = 'http://127.0.0.1:8080';
const OUT = '/home/user/youtube-subject-modify-auto/.harness-tmp/shots_new/out';
fs.mkdirSync(OUT, { recursive: true });
const log = [];
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', (e) => log.push('PAGEERROR ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') log.push('CONSOLE ' + m.text().slice(0, 200)); });
async function shot(name, vw = 900) {
  await page.setViewportSize({ width: 1280, height: vw });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  log.push('SHOT ' + name);
}
async function step(name, fn) {
  try { await fn(); } catch (e) { log.push('FAIL ' + name + ' :: ' + String(e.message).split('\n')[0]); try { await page.screenshot({ path: `${OUT}/_fail_${name}.png` }); } catch {} }
}

await step('01-home-empty', async () => {
  await page.goto(`${BASE}/#/`); await page.getByRole('heading', { name: '홈', exact: true }).waitFor();
  await page.getByRole('button', { name: '데모 영상 불러오기' }).waitFor();
  await shot('01-home-empty');
});
await step('02-home-synced', async () => {
  await page.getByRole('button', { name: '데모 영상 불러오기' }).click();
  await page.getByText('200', { exact: true }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(1500);
  await shot('02-home-synced');
});
await step('03-videos', async () => {
  await page.goto(`${BASE}/#/videos`); await page.getByRole('table').waitFor();
  await page.locator('tbody tr').nth(5).waitFor();
  await shot('03-videos', 1250);
});
await step('04-generate-dialog', async () => {
  const boxes = page.locator('tbody input[type=checkbox]:not([disabled])');
  await boxes.nth(0).check(); await boxes.nth(1).check();
  await page.getByRole('button', { name: /선택 영상 AI 제안 생성/ }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByText(/처리됨/).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(1500);
  await shot('04-generate-dialog');
  await page.getByRole('button', { name: '닫기' }).click();
});
await step('05-detail', async () => {
  await page.goto(`${BASE}/#/videos/demoVid0001`);
  await page.getByRole('heading', { name: '제안 목록' }).waitFor();
  await page.getByText('변경 전/후 비교').first().waitFor({ timeout: 20000 });
  await shot('05-detail', 2300);
});
await step('06-approve-dialog', async () => {
  const btn = page.getByRole('button', { name: '승인', exact: true }).first();
  await btn.click();
  await page.getByRole('dialog').waitFor();
  const name = page.getByLabel('승인자 이름'); if (await name.count()) await name.fill('검증자');
  const ack = page.getByLabel(/경고 사유를 모두 읽고/); if (await ack.count()) await ack.check();
  await shot('06-approve-dialog');
  await page.getByRole('dialog').getByRole('button', { name: /^승인/ }).last().click();
  await page.getByText('승인했습니다.').first().waitFor({ timeout: 15000 });
});
await step('07-detail-approved', async () => {
  await page.waitForTimeout(800); await shot('07-detail-approved', 2300);
});
await step('08-batches-select', async () => {
  await page.goto(`${BASE}/#/batches`);
  await page.getByText('반영할 승인 항목 고르기').waitFor();
  await page.locator('input[type=checkbox]').first().waitFor({ timeout: 15000 });
  await page.waitForTimeout(800);
  await page.locator('input[type=checkbox]').nth(1).check();
  await shot('08-batches-select');
});
await step('09-precheck', async () => {
  await page.getByRole('button', { name: '사전 점검 만들기' }).click();
  await page.getByText('사전 점검(미리보기)').waitFor({ timeout: 20000 });
  await page.waitForTimeout(800);
  await shot('09-precheck', 2000);
});
await step('10-confirm-executed', async () => {
  const ab = page.getByLabel(/A\/B 테스트 중이 아님을 확인했습니다/); if (await ab.count()) await ab.check();
  const inp = page.getByLabel(/확인 문구/); await inp.fill('실행 1건');
  await shot('10-confirm-ready', 2000);
  await page.getByRole('button', { name: '실행', exact: true }).click();
  await page.getByText('이 배치는 끝났습니다').waitFor({ timeout: 40000 });
  await page.waitForTimeout(800);
  await shot('11-executed');
});
await step('12-history', async () => {
  await page.goto(`${BASE}/#/history`); await page.locator('main table').waitFor();
  await page.waitForTimeout(600); await shot('12-history');
});
await step('13-rollback-dialog', async () => {
  await page.getByRole('button', { name: '롤백' }).first().click();
  await page.getByRole('dialog').waitFor();
  const id = page.getByLabel(/영상 ID/); if (await id.count()) await id.first().fill('demoVid0001');
  const ap = page.getByLabel(/승인자|실행자|이름/); if (await ap.count()) await ap.first().fill('검증자');
  await shot('13-rollback-dialog');
  await page.keyboard.press('Escape');
});
await step('14-reports', async () => {
  await page.goto(`${BASE}/#/reports`); await page.getByRole('heading', { name: '성과 리포트' }).waitFor();
  await page.waitForTimeout(1500); await shot('14-reports');
});
await step('15-settings', async () => {
  await page.goto(`${BASE}/#/settings`); await page.getByRole('heading', { name: '설정', exact: true }).waitFor();
  await page.waitForTimeout(1200); await shot('15-settings');
});
await b.close();
fs.writeFileSync(`${OUT}/_log.txt`, log.join('\n'));
console.log(log.join('\n'));
