import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { video, suggestion } from '../../frontend/src/test/fixtures';
import { connectedClient, json, renderWithApp, route } from '../../frontend/src/test/utils';
import { VideosPage } from '../../frontend/src/pages/VideosPage';
import { SuggestionCard } from '../../frontend/src/pages/SuggestionCard';
import { TitleDiff } from '../../frontend/src/components/TitleDiff';
import { render } from '@testing-library/react';

const EVIL = [
  '<script>alert(1)</script>',
  '"><img src=x onerror=alert(1)>',
  '<svg onload=alert(1)>',
  'javascript:alert(1)',
  '＜script＞alert(1)＜/script＞',
  '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
  '<a href="javascript:alert(1)">x</a>',
  '‮<b onmouseover=alert(1)>',
];
function assertClean(root: HTMLElement) {
  expect(root.querySelectorAll('script,iframe,img,svg,object,embed,style').length).toBe(0);
  root.querySelectorAll('*').forEach((el) => {
    for (const a of Array.from(el.attributes)) {
      expect(a.name.toLowerCase().startsWith('on')).toBe(false);
      if (['href', 'src', 'srcdoc'].includes(a.name)) expect(a.value.toLowerCase()).not.toContain('javascript:');
    }
  });
}

describe('저장형 XSS 렌더', () => {
  it.each(EVIL)('영상 목록 제목 %s', async (evil) => {
    const { client } = await connectedClient([
      route('GET', '/api/v1/videos', () => json(200, { items: [video(1, { title: evil })], total: 1, page: 1, page_size: 50 })),
    ]);
    const { container } = renderWithApp(<VideosPage />, client, '/videos');
    await screen.findAllByText((t) => t.includes('alert(1)') || t.includes('javascript'));
    assertClean(container);
    expect(container.textContent).toContain(evil.replace(/‮/, '').slice(0, 5));
  });
  it.each(EVIL)('제안 카드 제목·근거·승인자 %s', async (evil) => {
    const { client } = await connectedClient([]);
    const s = suggestion(1, { title: evil, evidence: evil, reasons: [evil], status: 'approved', approval: { approver: evil, approved_at: '2026-10-10T00:00:00Z' } } as never);
    const { container } = renderWithApp(<SuggestionCard s={s} currentTitle={evil} />, client, '/');
    assertClean(container);
    expect(container.textContent).toContain(evil.slice(0, 5));
  });
  it.each(EVIL)('TitleDiff %s', (evil) => {
    const { container } = render(<TitleDiff before={evil} after={evil + '추가'} />);
    assertClean(container);
  });
});

describe('양성 대조군(검사기가 실제로 잡는지)', () => {
  it('innerHTML 로 렌더하면 검사가 실패해야 한다', () => {
    const { container } = render(<div dangerouslySetInnerHTML={{ __html: '<img src=x onerror=alert(1)>' }} />);
    expect(() => assertClean(container)).toThrow();
  });
});
