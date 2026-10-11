import pytest

from youtube_title.config import load_settings
from youtube_title.errors import ConfigError


def write(path, text):
    path.write_text(text, encoding="utf-8")


def test_defaults_without_files(project):
    """TC-001: 설정 파일이 없어도 기본값(60% 상한, 72시간, 3회, 1,000회)으로 로드된다. [NFR-003, SEC-004]"""
    s = load_settings(project, env={})
    assert (s.daily_limit_units, s.min_interval_hours, s.max_changes_per_video, s.min_impressions_before_rechange) == (6000, 72, 3, 1000)
    assert s.enable_live is False and s.live_allowlist == ()


def test_settings_yaml_overrides_default(project):
    """TC-002: settings.yaml 값이 기본값을 덮어쓴다. [FR-017]"""
    write(project / "config" / "settings.yaml", "quota:\n  daily_limit_units: 5000\n")
    assert load_settings(project, env={}).daily_limit_units == 5000


def test_local_overrides_base(project):
    """TC-003: settings.local.yaml이 settings.yaml보다 우선한다. [ADR-010]"""
    write(project / "config" / "settings.yaml", "quota:\n  daily_limit_units: 5000\n")
    write(project / "config" / "settings.local.yaml", "quota:\n  daily_limit_units: 4000\n")
    assert load_settings(project, env={}).daily_limit_units == 4000


def test_live_in_base_is_ignored_with_warning(project):
    """TC-004: settings.yaml의 live.enable_live=true는 무시되고 경고가 남는다. [SEC-001]"""
    write(project / "config" / "settings.yaml", "live:\n  enable_live: true\n  live_allowlist: [abc123DEF45]\n")
    s = load_settings(project, env={})
    assert s.enable_live is False and s.live_allowlist == ()
    assert s.warnings and "settings.local.yaml" in s.warnings[0]


def test_live_in_local_is_honored(project):
    """TC-005: settings.local.yaml의 live 값은 적용된다. [SEC-001, SEC-012]"""
    write(project / "config" / "settings.local.yaml", "live:\n  enable_live: true\n  live_allowlist: [abc123DEF45]\n")
    s = load_settings(project, env={})
    assert s.enable_live is True and s.live_allowlist == ("abc123DEF45",)


@pytest.mark.parametrize("yaml_text", [
    "quota:\n  daily_limit_units: abc\n",
    "quota:\n  daily_limit_units: -1\n",
    "quota:\n  warn_ratio: 1.5\n",
    "validation:\n  hard_max_chars: 101\n",
    "cadence:\n  max_changes_per_video: 0\n",
    "sequential_mode:\n  enabled: \"yes\"\n",
    "quota:\n  daily_limit_units: true\n",
    "quota:\n  daily_limit_units: 10.5\n",
])
def test_invalid_values_raise_korean_config_error(project, yaml_text):
    """TC-006: 형식·범위가 잘못된 설정은 한국어 안내가 있는 ConfigError가 된다. [NFR-007]"""
    write(project / "config" / "settings.yaml", yaml_text)
    with pytest.raises(ConfigError) as ei:
        load_settings(project, env={})
    assert ei.value.next_step


def test_length_and_ratio_order_validated(project):
    """TC-007: 제목 길이(핵심어≤권장≤상한)와 일치율(차단≤경고) 순서가 틀리면 거부한다. [FR-002]"""
    write(project / "config" / "settings.yaml", "validation:\n  key_phrase_chars: 50\n  recommended_max_chars: 40\n")
    with pytest.raises(ConfigError):
        load_settings(project, env={})
    write(project / "config" / "settings.yaml", "validation:\n  warn_match_ratio: 0.2\n  block_match_ratio: 0.4\n")
    with pytest.raises(ConfigError):
        load_settings(project, env={})


def test_yaml_syntax_error_and_non_mapping(project):
    """TC-008: YAML 문법 오류, 최상위가 목록인 파일은 ConfigError. 위험한 태그는 safe_load로 실행되지 않는다. [SEC-016]"""
    write(project / "config" / "settings.yaml", "quota: [unclosed\n")
    with pytest.raises(ConfigError):
        load_settings(project, env={})
    write(project / "config" / "settings.yaml", "- a\n- b\n")
    with pytest.raises(ConfigError):
        load_settings(project, env={})
    marker = project / "pwned"
    write(project / "config" / "settings.yaml", f"quota: !!python/object/apply:os.mkdir ['{marker.as_posix()}']\n")
    with pytest.raises(ConfigError):
        load_settings(project, env={})
    assert not marker.exists()  # 위험한 태그가 실제로 실행되지 않았다(safe_load)


def test_allowlist_must_be_string_list(project):
    """TC-009: live_allowlist가 문자열 목록이 아니면 거부한다. [SEC-012]"""
    write(project / "config" / "settings.local.yaml", "live:\n  live_allowlist: [1, 2]\n")
    with pytest.raises(ConfigError):
        load_settings(project, env={})


def test_env_paths_and_token_dir_outside_project(project, tmp_path):
    """TC-010: .env/환경변수로 경로를 지정하고, 기본 토큰 폴더는 프로젝트 밖이다. [SEC-008, ADR-004]"""
    write(project / ".env", "YT_DATA_DIR=mydata\n")
    s = load_settings(project, env={})
    assert s.data_dir == project.resolve() / "mydata" and s.db_path.parent == s.data_dir
    assert project.resolve() not in s.token_dir.parents
    s2 = load_settings(project, env={"YT_TOKEN_DIR": str(tmp_path / "tok")})
    assert s2.token_dir == tmp_path / "tok"
