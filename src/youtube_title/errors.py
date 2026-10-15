"""공통 예외. 모든 메시지는 한국어이며 '다음에 할 일'을 함께 담는다(NFR-007)."""


class YtError(Exception):
    code = "YT-000"
    exit_code = 1

    def __init__(self, message: str, next_step: str = "", *, cause: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.next_step = next_step
        self.cause = cause


class ConfigError(YtError):
    code = "YT-100"


class DatabaseError(YtError):
    code = "YT-200"


class QuotaError(YtError):
    code = "YT-300"


class AuthError(YtError):
    code = "YT-400"


class InputError(YtError):
    code = "YT-500"


class SafetyGateError(YtError):
    """쓰기 안전 게이트에서 중단됨(종료 코드 3)."""

    code = "YT-600"
    exit_code = 3


class ApiError(YtError):
    code = "YT-700"

    def __init__(self, message: str, next_step: str = "", *, retryable: bool = False, cause: str = "") -> None:
        super().__init__(message, next_step, cause=cause)
        self.retryable = retryable
