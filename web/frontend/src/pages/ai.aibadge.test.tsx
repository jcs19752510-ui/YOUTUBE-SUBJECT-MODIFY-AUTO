import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { detail, suggestion, dashboard } from '../test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { HomePage } from './HomePage';
import { VideoDetailPage } from './VideoDetailPage';

const ui = (
  <Routes>
    <Route path="videos/:videoId" element={<VideoDetailPage />} />
  </Routes>
);
const show = async (source: string) => {
  const c = await connectedClient([
    route('GET', '/api/v1/videos/vid00000001', () =>
      json(200, detail([suggestion(1, { source, evidence: '영상 설명의 한 문장' })])),
    ),
  ]);
  renderWithApp(ui, c.client, '/videos/vid00000001');
  await screen.findByText('테스트 영상 1 핵심 정리');
  return document.querySelector<HTMLElement>('#sg-1')!.closest('article') as HTMLElement;
};

describe('AI 제안 종류 표시 (DEF-LIVE-006)', () => {
  it('모의 제안은 연습용 모의 제안(데모)로 보인다', async () => {
    const a = await show('ai:mock');
    expect(within(a).getByText('연습용 모의 제안(데모)')).toBeInTheDocument();
  });
  it('규칙 기반 제안은 규칙 기반 제안으로 보인다', async () => {
    const a = await show('ai:rule');
    expect(
      within(a).getByText('규칙 기반 제안(영상 설명의 장면 제목을 조합)'),
    ).toBeInTheDocument();
    expect(within(a).queryByText(/모의|데모/)).toBeNull();
  });
  it('Gemini 제안은 Gemini AI 제안으로 보인다', async () => {
    const a = await show('ai:gemini');
    expect(within(a).getByText('Gemini AI 제안')).toBeInTheDocument();
    expect(within(a).queryByText(/모의|데모/)).toBeNull();
  });
  it('직접 고친 제안은 종류와 함께 직접 고침을 알린다', async () => {
    const a = await show('ai:gemini+edited');
    expect(within(a).getByText('Gemini AI 제안(직접 고침)')).toBeInTheDocument();
  });
  it('종류 정보가 없는 옛 제안은 그냥 AI 제안으로 보인다', async () => {
    const a = await show('ai');
    expect(within(a).getByText('AI 제안')).toBeInTheDocument();
  });
});

describe('구글 연결 상태에서는 데모 안내를 숨긴다 (DEF-LIVE-006)', () => {
  const noVideos = { videos: 0, excluded: 0, suggested: 0, approved: 0, queued: 0, applied: 0 };
  const home = async (over: Parameters<typeof dashboard>[0]) => {
    const c = await connectedClient([
      route('GET', '/api/v1/dashboard', () => json(200, dashboard({ counts: noVideos, ...over }))),
    ]);
    renderWithApp(<HomePage />, c.client);
  };
  it('데모 모드에서는 데모 영상 안내가 그대로 있다', async () => {
    await home({});
    expect(await screen.findByText(/데모 영상 200개를 불러와/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '데모 영상 불러오기' })).toBeInTheDocument();
  });
  it('구글 연결(읽기) 상태에서는 데모 영상 안내와 버튼이 없다', async () => {
    await home({ google: { mode: 'readonly', connected: true } });
    expect(await screen.findByText(/아래 "구글\(유튜브\) 연결" 카드/)).toBeInTheDocument();
    expect(screen.queryByText(/데모 영상 200개/)).toBeNull();
    expect(screen.queryByRole('button', { name: '데모 영상 불러오기' })).toBeNull();
  });
});
