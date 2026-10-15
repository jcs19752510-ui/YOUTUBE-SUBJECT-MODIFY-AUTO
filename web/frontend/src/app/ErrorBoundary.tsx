import { Component, type ReactNode } from 'react';
import { Callout } from '../components';
import { ko } from '../i18n/ko';

/**
 * 화면 하나가 예기치 않게 깨져도(서버 응답 형식이 계약과 다른 경우 등) 메뉴와 안내는 남긴다.
 * 오류 내용(스택 등)은 화면에 보이지 않는다. 화면을 옮기면(resetKey 변경) 다시 시도한다.
 */
export class ErrorBoundary extends Component<
  { resetKey: string; children: ReactNode },
  { failed: boolean }
> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidUpdate(prev: { resetKey: string }): void {
    if (prev.resetKey !== this.props.resetKey && this.state.failed) {
      this.setState({ failed: false });
    }
  }

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <Callout tone="danger" role="alert" title={ko.app.crashTitle}>
        <p>{ko.app.crashBody}</p>
        <p>
          <strong>{ko.state.nextStep}:</strong> {ko.app.crashNext}
        </p>
        <button type="button" className="btn btn--sm" onClick={() => window.location.reload()}>
          {ko.app.reload}
        </button>
      </Callout>
    );
  }
}
