import type { ReactNode } from 'react';

/** 로그인·계정 만들기 공통 카드: 회색 배경 위 가운데 흰 카드, 가운데 정렬 제목. */
export function AuthCard({ title, body, children }: { title: string; body?: string; children: ReactNode }) {
  return (
    <main className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">{title}</h1>
        {body && <p className="auth-card__body">{body}</p>}
        {children}
      </div>
    </main>
  );
}
