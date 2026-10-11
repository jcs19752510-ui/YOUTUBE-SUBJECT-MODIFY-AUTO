"""auth: 구글 로그인(읽기/쓰기 권한 분리, EVT-001, FR-016)."""
from __future__ import annotations

from ytitle import auth as authmod
from ytitle.errors import InputError
from ytitle.ui import badge, footer, render_table, title_line

NAME = "auth"
WRITE_CONFIRM = "쓰기권한"


def register(sub, parent):
    p = sub.add_parser(
        "auth",
        parents=[parent],
        help="구글 로그인(읽기/쓰기 권한은 따로)",
        description="읽기 권한(영상 조회·지표)과 쓰기 권한(제목 수정)을 따로 로그인합니다. 옵션 없이 실행하면 로그인 상태만 보여 줍니다.",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--read", action="store_true", help="읽기 권한으로 로그인(영상 조회, 지표 수집)")
    g.add_argument("--write", action="store_true", help="쓰기 권한으로 로그인(제목 수정용, 12단계 직전에만)")
    g.add_argument("--revoke", action="store_true", help="이 PC에 저장된 로그인 정보를 모두 삭제")
    p.set_defaults(func=run)


def _show_status(ctx) -> None:
    rows = [[("읽기" if s["kind"] == "read" else "쓰기"), badge("done") + " 저장됨" if s["exists"] else badge("caution") + " 없음", str(s["path"])] for s in authmod.status(ctx.settings)]
    ctx.say(render_table(["권한", "상태", "저장 위치"], rows, ctx.ui))


def run(args, ctx) -> int:
    ctx.say(title_line("auth", False))
    if args.revoke:
        removed = authmod.revoke(ctx.settings)
        ctx.say(f"{badge('done')} 이 PC의 로그인 정보 {len(removed)}개를 삭제했습니다.")
        ctx.say("구글 쪽 접근도 끊으려면 구글 계정 → 보안 → '타사 앱 및 서비스'에서 이 앱의 접근 권한을 삭제하세요.")
    elif args.read or args.write:
        kind = "write" if args.write else "read"
        if kind == "write":
            ctx.say("★ 쓰기 권한은 내 채널의 영상 제목을 바꿀 수 있는 권한입니다. 12단계 직전에만 받으세요.")
            if not ctx.confirm(WRITE_CONFIRM):
                raise InputError("확인이 완료되지 않아 쓰기 로그인을 취소했습니다.", "필요할 때 다시 실행하세요.")
        path, secured = authmod.login(kind, ctx.settings)
        ctx.say(f"{badge('done')} {'쓰기' if kind == 'write' else '읽기'} 권한 로그인을 저장했습니다: {path}")
        if not secured:
            ctx.say(f"{badge('caution')} 파일 접근 권한을 이 계정 전용으로 제한하지 못했습니다. 이 PC를 다른 사람과 함께 쓰면 폴더 권한을 직접 확인하세요.")
    else:
        _show_status(ctx)
        ctx.say("처음이면 `python -m ytitle auth --read`로 읽기 로그인부터 하세요.")
    ctx.say(footer())
    return 0
