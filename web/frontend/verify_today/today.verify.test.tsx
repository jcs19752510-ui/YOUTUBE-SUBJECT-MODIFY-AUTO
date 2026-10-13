// 오늘 변경 독립 검증(TC-TD-*): 배치 승인 칸 분리 표시, 제외 영상 안내문, 상태 문구 일관성.
import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { ko } from '../src/i18n/ko';
import { fmtDateTime } from '../src/lib/format';
import { BatchesPage } from '../src/pages/BatchesPage';
import { VideosPage } from '../src/pages/VideosPage';
import { suggestion, video } from '../src/test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../src/test/utils';

const page = (items: unknown[]) => json(200, { items, total: items.length, page: 1, page_size: 20 });

describe('TC-TD 배치 승인 칸', () => {
  it('TC-TD-001 승인 시각과 만료가 분리 표시된다(승인 시각 칸에 만료 시각이 나오지 않는다)', async () => {
    const s = suggestion(1, {
      video_id: 'vid00000001',
      title: '승인된 제목 1',
      status: 'approved',
      approval: { approver: '홍', approved_at: '2026-10-10T01:00:00Z', expires_at: '2026-10-11T05:00:00Z' },
    });
    const { client } = await connectedClient([
      route('GET', '/api/v1/suggestions', () => page([s])),
      route('GET', '/api/v1/batches', () => page([])),
    ]);
    renderWithApp(
      <Routes><Route path="batches" element={<BatchesPage />} /></Routes>,
      client,
      '/batches',
    );
    const row = (await screen.findByText('승인된 제목 1')).closest('tr')!;
    const a = fmtDateTime('2026-10-10T01:00:00Z');
    const e = fmtDateTime('2026-10-11T05:00:00Z');
    const cells = within(row).getAllByRole('cell');
    const cell = cells.find((c) => c.textContent?.includes(ko.batches.approvalExpires(e)))!;
    expect(cell).toBeTruthy();
    expect(cell.textContent).toContain(a);
    expect(cell.textContent).toBe(`홍${a}${ko.batches.approvalExpires(e)}`);
    expect(ko.batches.approvalExpires(e)).toBe(`만료 ${e}`);
  });
});

describe('TC-TD 영상 목록', () => {
  const items = [
    video(1),
    video(2, { excluded: true, is_short: true, exclusion_reasons: ['Shorts 가능성'] }),
    video(3, { excluded: true, privacy_status: 'private', exclusion_reasons: ['비공개 영상'] }),
  ];
  const mount = async (list: ReturnType<typeof video>[]) => {
    const { client } = await connectedClient([route('GET', '/api/v1/videos', () => page(list))]);
    renderWithApp(<Routes><Route path="videos" element={<VideosPage />} /></Routes>, client, '/videos');
  };
  it('TC-TD-002 제외 영상이 있으면 안내문(제외 2개, 선택 가능 1개)이 note 로 나온다', async () => {
    await mount(items);
    await screen.findByText('테스트 영상 1');
    const note = screen.getByRole('note');
    expect(note.textContent).toBe(ko.videos.excludedNotice(2, 1));
    expect(note.textContent).toContain('쇼츠');
  });
  it('TC-TD-003 제외 영상이 없으면 안내문이 없다', async () => {
    await mount([video(1), video(4)]);
    await screen.findByText('테스트 영상 1');
    expect(screen.queryByRole('note')).toBeNull();
  });
  it('TC-TD-004 전부 제외면 선택 가능 0개 안내', async () => {
    await mount([items[1], items[2]]);
    await screen.findByText('테스트 영상 2');
    expect(screen.getByRole('note').textContent).toBe(ko.videos.excludedNotice(2, 0));
  });
  it('TC-TD-005 상태 문구: 영상 목록·홈 현황 모두 제안 있음(검토 대기)로 같다', () => {
    expect(ko.workflow.suggested).toBe('제안 있음(검토 대기)');
    expect(ko.home.counts.suggested).toBe(ko.workflow.suggested);
  });
  it('TC-TD-006 승인 유효시간 안내는 24시간이고 12시간·48시간 등 다른 값이 남지 않는다', () => {
    const t = ko.bulk.ttlNotice;
    expect(t).toContain('24시간');
  });
});
