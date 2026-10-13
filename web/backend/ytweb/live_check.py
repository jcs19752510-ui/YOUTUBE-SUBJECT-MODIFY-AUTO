"""실제 제목 수정 준비 상태 점검(읽기 전용, 네트워크 호출 없음): `python -m ytweb.live_check`.
구글 연결 파일·읽기/쓰기 로그인·실제 수정 스위치·허용 영상을 확인해 빠진 것을 쉬운 말로 알려 준다. 아무것도 바꾸지 않는다."""
from __future__ import annotations

import os
from pathlib import Path

from ytweb.domain import live_gateway as lg
from ytweb.youtube import google_oauth as oauth


def check(env: dict[str, str] | None = None, secrets_dir: Path | None = None) -> tuple[list[tuple[bool, str]], bool]:
    e = dict(os.environ if env is None else env)
    sd = secrets_dir or Path(e.get("YTWEB_SECRETS_DIR", "/var/lib/ytweb/secrets"))
    client = Path(e.get("YTWEB_GOOGLE_CLIENT_FILE", "/run/secrets/google_client"))
    allowed = lg.allowed_videos(e)
    items = [
        (client.is_file(), "구글 연결 파일(web\\secrets\\google_client.json)이 있다" if client.is_file()
         else "구글 연결 파일이 없다 → web\\secrets\\google_client.json 을 저장한 뒤 start.ps1 을 다시 실행하세요"),
        (oauth.TokenStore(sd / "google_token.json").load() is not None, "읽기 로그인이 되어 있다" if oauth.TokenStore(sd / "google_token.json").load() is not None
         else "읽기 로그인이 안 되어 있다 → 화면의 [구글 계정 연결]을 누르세요"),
        (oauth.TokenStore(sd / lg.WRITE_TOKEN_FILE).load() is not None, "제목 수정 권한이 연결되어 있다" if oauth.TokenStore(sd / lg.WRITE_TOKEN_FILE).load() is not None
         else "제목 수정 권한이 없다 → 화면의 [제목 수정 권한 연결]을 누르세요"),
        (lg.live_write_enabled(e), "실제 수정 스위치가 켜져 있다(YTWEB_LIVE_WRITE=1)" if lg.live_write_enabled(e)
         else "실제 수정 스위치가 꺼져 있다 → web\\.env 의 YTWEB_LIVE_WRITE=1 로 바꾸고 start.ps1 을 다시 실행하세요"),
        (bool(allowed), f"수정을 허용한 영상이 {len(allowed)}개 있다" if allowed
         else "수정을 허용한 영상이 없다 → web\\.env 의 YTWEB_LIVE_ALLOWED_VIDEOS 에 테스트 영상 ID를 넣고 start.ps1 을 다시 실행하세요"),
    ]
    return items, all(ok for ok, _ in items)


def main() -> int:
    items, ready = check()
    print("--- 실제 제목 수정 준비 상태 ---")
    for ok, msg in items:
        print(("[OK]  " if ok else "[필요] ") + msg)
    from ytweb.domain.exclusions import include_shorts
    print("[정보] 쇼츠(180초 이하) 영상 제목 변경: " + ("켜짐(YTWEB_INCLUDE_SHORTS=1)" if include_shorts()
          else "꺼짐 → 쇼츠도 바꾸려면 web\\.env 에 YTWEB_INCLUDE_SHORTS=1 을 넣고 start.ps1 을 다시 실행한 뒤 홈의 [내 영상 불러오기]를 누르세요"))
    print("")
    print("결과: 실제 수정이 가능한 상태입니다. 허용된 영상의 제목만 실제 유튜브에서 바뀝니다." if ready
          else "결과: 아직 실제 수정은 꺼져 있습니다(위 [필요] 항목을 하면 켜집니다). 지금은 실제 유튜브가 바뀌지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
