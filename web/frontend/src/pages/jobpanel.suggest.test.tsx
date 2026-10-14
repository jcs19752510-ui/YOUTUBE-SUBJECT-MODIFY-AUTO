import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { connectedClient, json, renderWithApp, route } from '../test/utils';
import { JobPanel } from './JobPanel';

const job = (result: Record<string, unknown>) =>
  json(200, { id: 'j1', type: 'suggestions.generate', status: 'succeeded', progress: 1, total: 1, error: null, result });

async function show(result: Record<string, unknown>) {
  const c = await connectedClient([route('GET', '/api/v1/jobs/j1', () => job(result))]);
  renderWithApp(<JobPanel jobId="j1" label="AI 제안 생성" />, c.client);
}

describe('AI 제안 생성 결과 요약(2026-10-14)', () => {
  it('TC-FE-JOB-001 영상이 건너뛰어졌으면 완료여도 영상 ID 와 이유가 보인다(제안 0건)', async () => {
    await show({
      videos: 1,
      suggestions: 0,
      skipped: [{ video_id: 'vid00000001', code: 'ai_no_pass_candidates', reason: '만든 후보가 모두 검증을 통과하지 못해 저장하지 않았습니다.' }],
    });
    expect(await screen.findByText('AI 제안 0건을 만들었습니다.')).toBeInTheDocument();
    expect(screen.getByText(/제안을 만들지 못한 영상 1개/)).toBeInTheDocument();
    expect(screen.getByText(/vid00000001/)).toBeInTheDocument();
    expect(screen.getByText(/검증을 통과하지 못해/)).toBeInTheDocument();
  });
  it('TC-FE-JOB-002 모두 만들었으면 건수만 보이고 실패 안내는 없다', async () => {
    await show({ videos: 1, suggestions: 3, skipped: [] });
    expect(await screen.findByText('AI 제안 3건을 만들었습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/만들지 못한 영상/)).toBeNull();
  });
  it('TC-FE-JOB-003 다른 종류 작업(제안 수 없음)에는 요약이 나오지 않는다', async () => {
    await show({ created: 5 });
    expect(await screen.findByText(/처리됨/)).toBeInTheDocument();
    expect(screen.queryByText(/AI 제안/)).toBeNull();
  });
});
