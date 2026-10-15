/** 화면 이동(구글 로그인 창으로 이동할 때 사용). 시험에서 대체할 수 있도록 분리했다. */
export function navigateTo(url: string): void {
  window.location.assign(url);
}
