import logging

import pytest

from ytitle.logging_setup import MASK, mask, setup_logging

SECRETS = [
    "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "1//0gAbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "GOCSPX-abcDEF123_ghiJKL456",
    "Bearer abc.def-ghi_jkl",
    '{"client_secret": "s3cr3tvalue"}',
    "refresh_token=abcdef123456",
    "A" * 45,
]


@pytest.mark.parametrize("secret", SECRETS)
def test_mask_hides_each_secret_format(secret):
    """TC-011: 토큰·키 형식(액세스/리프레시 토큰, GOCSPX, Bearer, JSON 키, 긴 문자열)이 가려진다. [SEC-008, K-6]"""
    out = mask(f"요청 실패 {secret} 끝")
    for frag in ("ya29.a0", "0gAbCd", "GOCSPX-abc", "abc.def-ghi", "s3cr3tvalue", "abcdef123456", "A" * 45):
        assert frag not in out
    assert MASK in out


def test_mask_keeps_normal_text_and_video_id():
    """TC-012: 일반 한글 문장과 11자 영상 ID는 가리지 않는다(과잉 마스킹 방지). [NFR-011]"""
    text = "영상 abc123DEF45 제목을 확인했습니다"
    assert mask(text) == text


def test_log_file_masks_message_args_and_traceback(tmp_path):
    """TC-013: 로그 파일에 메시지·인자·예외 추적 어디에도 비밀이 남지 않고 한글이 정상 저장된다. [SEC-008, NFR-002]"""
    logger = setup_logging(tmp_path, "run123")
    try:
        raise RuntimeError("토큰 ya29.zzzzzzzzzzzzzzzz 노출")
    except RuntimeError:
        logger.error("실패: %s", "Bearer topsecret.token", exc_info=True)
    for h in logger.handlers:
        h.flush()
    text = (tmp_path / "logs" / "ytitle.log").read_text(encoding="utf-8")
    assert "topsecret" not in text and "ya29.zzzz" not in text
    assert "run123" in text and "실패" in text


def test_setup_logging_replaces_handlers(tmp_path):
    """TC-014: setup_logging을 다시 호출해도 핸들러가 중복되지 않는다. [NFR-011]"""
    setup_logging(tmp_path, "a")
    logger = setup_logging(tmp_path, "b")
    assert len(logger.handlers) == 1
    assert logger.level == logging.INFO
