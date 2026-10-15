"""부하 시험용 앱 팩토리: 운영과 같은 create_app 이되 속도 제한만 해제(속도 제한은 시험 대상 아님). 로그는 켜 둔다."""
from ytweb.app import create_app as _c
from ytweb.core.ratelimit import RateLimits
def create_app():
    return _c(rate_limits=RateLimits(global_per_min=10**8, write_per_min=10**8, auth_per_min=10**8))
