import pytest

from ytitle.errors import ApiError
from ytitle.retry import MAX_RETRIES, call_with_retry


class Flaky:
    def __init__(self, fails, exc=None):
        self.fails, self.calls = fails, 0
        self.exc = exc or ApiError("일시 오류", retryable=True)

    def __call__(self):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.exc
        return "성공"


def test_succeeds_after_two_retries_with_exponential_backoff():
    """TC-015: 2번 실패 후 3번째 성공하며 대기는 1초→2초(지수 백오프). [SEC-003, NFR-004]"""
    sleeps = []
    f = Flaky(2)
    assert call_with_retry(f, sleep=sleeps.append) == "성공"
    assert f.calls == 3 and sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries():
    """TC-016: 계속 실패하면 총 3번(최초+재시도 2회)만 호출하고 예외를 올린다. 무한 재시도 없음. [SEC-003]"""
    f = Flaky(99)
    with pytest.raises(ApiError):
        call_with_retry(f, sleep=lambda s: None)
    assert f.calls == 1 + MAX_RETRIES == 3


def test_retries_parameter_is_capped():
    """TC-017: retries에 큰 값을 줘도 상한(2회)을 넘지 않는다. [SEC-003]"""
    f = Flaky(99)
    with pytest.raises(ApiError):
        call_with_retry(f, retries=50, sleep=lambda s: None)
    assert f.calls == 3


def test_non_retryable_error_is_raised_immediately():
    """TC-018: 재시도 불가 오류(인증·할당량 등)는 재시도하지 않는다. [SEC-003]"""
    f = Flaky(5, ApiError("권한 없음", retryable=False))
    with pytest.raises(ApiError):
        call_with_retry(f, sleep=lambda s: None)
    assert f.calls == 1


def test_connection_errors_and_http_5xx_are_retryable():
    """TC-019: 연결 오류와 HTTP 5xx는 재시도 대상, 4xx는 아니다. [NFR-004]"""
    class Resp:
        def __init__(self, status): self.status = status

    class Http(Exception):
        def __init__(self, status): self.resp = Resp(status)

    assert call_with_retry(Flaky(1, ConnectionError()), sleep=lambda s: None) == "성공"
    assert call_with_retry(Flaky(1, Http(503)), sleep=lambda s: None) == "성공"
    f = Flaky(1, Http(404))
    with pytest.raises(Http):
        call_with_retry(f, sleep=lambda s: None)
    assert f.calls == 1


def test_on_retry_callback_and_zero_retries():
    """TC-020: 재시도 콜백이 호출되고, retries=0이면 재시도하지 않는다. [NFR-004]"""
    seen = []
    call_with_retry(Flaky(1), sleep=lambda s: None, on_retry=lambda n, e: seen.append(n))
    assert seen == [1]
    f = Flaky(1)
    with pytest.raises(ApiError):
        call_with_retry(f, retries=0, sleep=lambda s: None)
    assert f.calls == 1
