"""YouTube Studio에서 내보낸 CSV 가져오기(FR-007, EVT-203, SEC-016, T-11).

CSV는 신뢰할 수 없는 외부 입력이다. 이 모듈은 셀을 **값(숫자·문자열)으로만** 읽고, 수식·코드로 해석하거나 실행하지 않는다.
크기·행 수 상한을 두고, 불량 행은 건너뛰며 그 개수와 이유를 모아서 알린다(전체 중단 아님).
네트워크 호출은 없다. DB에는 `metrics_snapshots`(source='csv')에만 쓴다(SQL은 파라미터 바인딩만, SEC-018).
"""
from __future__ import annotations

import codecs
import csv
import io
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from youtube_title.errors import DatabaseError, InputError
from youtube_title.textsafe import normalize_for_match, sanitize_for_display
from youtube_title.timeutil import utc_iso

MAX_BYTES = 5 * 1024 * 1024  # 5MB
MAX_ROWS = 10_000
MAX_INT = 10**12
MAX_MINUTES = 10**9
PHASES = ("before", "after", "periodic")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
CELL_MAX = 200

# 머리글 별칭(한국어/영어). 비교할 때 textsafe.normalize_for_match로 공백·기호·대소문자를 지우므로 표기 차이는 신경 쓰지 않는다.
# Studio 내보내기의 실제 머리글은 [확인 필요]이며, 다르면 이 표만 고치면 된다. 단위를 알 수 없는 "시청 시간" 단독 열은 일부러 넣지 않았다(추측 금지).
_ALIASES_READABLE: dict[str, tuple[str, ...]] = {
    "video_id": ("video id", "video_id", "video", "content", "콘텐츠", "동영상 ID", "영상 ID", "동영상 아이디", "영상 아이디"),
    "impressions": ("impressions", "노출수", "노출 수", "노출"),
    "ctr": ("ctr", "click-through rate", "impressions click-through rate (%)", "impressions click-through rate", "노출 클릭률(%)", "노출 클릭률", "클릭률"),
    "views": ("views", "조회수", "조회 수"),
    "watch_minutes": ("watch time (minutes)", "watch_minutes", "estimatedMinutesWatched", "시청 시간(분)", "시청 시간(단위: 분)"),
    "watch_hours": ("watch time (hours)", "시청 시간(시간)", "시청 시간(단위: 시간)"),
}
ALIASES: dict[str, str] = {normalize_for_match(a): fld for fld, names in _ALIASES_READABLE.items() for a in names}
METRIC_FIELDS = ("impressions", "ctr", "views", "watch_minutes")
_TOTAL_LABELS = frozenset(normalize_for_match(x) for x in ("total", "합계", "전체", "grand total"))
_MISSING = frozenset({"", "-", "–", "—", "n/a", "na", "null", "none"})
_NUM_RE = re.compile(r"^(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?$")


@dataclass(frozen=True)
class CsvRow:
    line: int
    video_id: str
    impressions: int | None
    ctr: float | None  # 퍼센트 단위(3.2 = 3.2%)
    views: int | None
    watch_minutes: float | None
    raw: dict


@dataclass(frozen=True)
class RowIssue:
    line: int
    reason: str
    detail: str = ""


@dataclass
class CsvParseResult:
    rows: list[CsvRow] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    columns: dict[str, str] = field(default_factory=dict)  # 인식한 필드 -> 원래 머리글(정화됨)
    ignored_columns: list[str] = field(default_factory=list)
    encoding: str = "utf-8"
    data_rows: int = 0


@dataclass
class StoreResult:
    inserted: int = 0
    duplicates: int = 0
    unknown_videos: int = 0


def neutralize_formula(text: str) -> str:
    """스프레드시트가 수식으로 읽을 수 있는 시작 문자(= + - @)가 있으면 앞에 `'`를 붙여 값으로만 보이게 한다(CSV 인젝션 방어)."""
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def safe_cell(value: object, max_len: int = CELL_MAX) -> str:
    """CSV에서 온 문자열을 화면·기록용으로 정화한다: 제어문자 제거 + 길이 제한 + 수식 시작 문자 무력화."""
    return neutralize_formula(sanitize_for_display(value, max_len))


def decode_csv_bytes(raw: bytes) -> tuple[str, str]:
    """UTF-8(BOM 허용) -> UTF-16(BOM) -> CP949(엑셀 한글 저장) 순으로 해석한다."""
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return raw.decode("utf-16"), "utf-16"
        except UnicodeDecodeError as exc:
            raise InputError("CSV 파일을 읽을 수 없습니다(UTF-16 형식이 깨졌습니다).", "Studio에서 CSV를 다시 내보내거나, 엑셀에서 'CSV UTF-8'로 저장하세요.") from exc
    if b"\x00" in raw:
        raise InputError("텍스트 CSV 파일이 아닙니다(바이너리 내용이 들어 있습니다).", "Studio에서 내보낸 .csv 파일을 그대로 지정하세요. 엑셀 파일(.xlsx)은 'CSV UTF-8'로 다시 저장해야 합니다.")
    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp949"), "cp949"
    except UnicodeDecodeError as exc:
        raise InputError("CSV 파일의 글자 인코딩을 알 수 없습니다(UTF-8도 CP949도 아닙니다).", "엑셀 또는 메모장에서 'CSV UTF-8' / 'UTF-8' 인코딩으로 다시 저장하세요.") from exc


def _delimiter(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return max((",", "\t", ";"), key=first.count)  # 동률(구분 문자 없음)이면 앞의 쉼표


def parse_number(text: str, kind: str) -> tuple[int | float | None, str]:
    """셀 하나를 숫자로 읽는다. 반환 (값, 오류 사유). 값이 비어 있으면 (None, ""). kind: int | float | percent.

    쉼표 천단위와 `%`(percent일 때만)를 허용한다. 수식처럼 보이는 값(=,+,-,@로 시작)과 지수 표기·NaN·무한대는 거부한다.
    """
    s = text.strip().replace(" ", "")
    if s.casefold() in _MISSING:
        return None, ""
    if kind == "percent" and s.endswith("%"):
        s = s[:-1].strip()
    if not _NUM_RE.match(s):
        if s.startswith(FORMULA_STARTS):
            return None, "숫자가 아니라 수식처럼 보이는 값이어서 읽지 않았습니다"
        return None, "숫자 형식이 아닙니다"
    num = s.replace(",", "")
    if kind == "int":
        if "." in num:
            return None, "정수가 아닙니다"
        value = int(num)
        return (value, "") if value <= MAX_INT else (None, "값이 너무 큽니다")
    value = float(num)
    if kind == "percent":
        return (value, "") if value <= 100 else (None, "클릭률이 100%를 넘습니다")
    return (value, "") if value <= MAX_MINUTES else (None, "값이 너무 큽니다")


def _map_columns(header: list[str], default_video_id: str | None) -> tuple[dict[str, int], list[str], list[str]]:
    """머리글을 필드로 매핑한다. 반환 (필드->열 번호, 무시한 열, 오류 목록). 오류는 모아서 한 번에 알린다."""
    index: dict[str, int] = {}
    ignored: list[str] = []
    errors: list[str] = []
    for i, name in enumerate(header):
        fld = ALIASES.get(normalize_for_match(name))
        if fld is None:
            ignored.append(safe_cell(name, 40))
        elif fld in index:
            errors.append(f"같은 의미의 열이 둘 이상입니다: `{safe_cell(header[index[fld]], 40)}`, `{safe_cell(name, 40)}`")
        else:
            index[fld] = i
    if "watch_minutes" in index and "watch_hours" in index:
        ignored.append(safe_cell(header[index.pop("watch_hours")], 40))  # 분 단위가 있으면 시간 단위 열은 쓰지 않는다
    if "video_id" not in index and default_video_id is None:
        errors.append("영상 ID 열(`콘텐츠`/`Content`/`동영상 ID`/`Video ID` 등)이 없습니다. 한 영상만의 파일이면 `--video 영상ID`를 함께 쓰세요.")
    if not any(f in index for f in METRIC_FIELDS + ("watch_hours",)):
        errors.append("가져올 지표 열(`노출수`/`Impressions`, `노출 클릭률`/`CTR`, `조회수`/`Views`, `시청 시간(분/시간)`)이 하나도 없습니다.")
    return index, ignored, errors


def parse_csv_bytes(raw: bytes, default_video_id: str | None = None) -> CsvParseResult:
    """CSV 바이트를 읽어 유효한 행과 건너뛴 행(이유 포함)으로 나눈다. 순수 함수(입력 불변, DB·파일 접근 없음)."""
    if len(raw) > MAX_BYTES:
        raise InputError(f"CSV 파일이 너무 큽니다({len(raw) // 1024}KB > {MAX_BYTES // 1024}KB).", "필요한 기간·영상만 다시 내보내 크기를 줄이세요.")
    if default_video_id is not None and not VIDEO_ID_RE.match(default_video_id):
        raise InputError("영상 ID 형식이 올바르지 않습니다(영문·숫자·-·_ 11자).", "유튜브 주소의 v= 뒤 11글자를 그대로 입력하세요.")
    text, encoding = decode_csv_bytes(raw)
    result = CsvParseResult(encoding=encoding)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
    header: list[str] | None = None
    index: dict[str, int] = {}
    seen: set[str] = set()
    try:
        for cells in reader:
            if not any(c.strip() for c in cells):
                continue  # 빈 줄
            if header is None:
                header = cells
                index, result.ignored_columns, errors = _map_columns(header, default_video_id)
                if errors:
                    raise InputError("CSV 머리글에 고칠 곳이 있습니다:\n  - " + "\n  - ".join(errors), "Studio에서 내보낸 파일의 첫 줄(머리글)을 바꾸지 말고 그대로 지정하세요. 머리글 이름이 다르면 알려 주세요.")
                result.columns = {f: safe_cell(header[i], 40) for f, i in index.items()}
                continue
            result.data_rows += 1
            if result.data_rows > MAX_ROWS:
                raise InputError(f"CSV 행이 너무 많습니다(최대 {MAX_ROWS:,}행).", "기간이나 영상 수를 줄여 나누어 가져오세요.")
            _parse_row(cells, reader.line_num, header, index, default_video_id, seen, result)
    except csv.Error as exc:
        raise InputError(f"CSV 형식이 올바르지 않습니다({safe_cell(exc, 80)}).", "Studio에서 CSV를 다시 내보내거나, 따옴표가 깨지지 않았는지 확인하세요.") from exc
    if header is None:
        raise InputError("CSV 파일이 비어 있습니다.", "Studio에서 내보낸 파일이 맞는지 확인하세요.")
    return result


def _parse_row(cells: list[str], line: int, header: list[str], index: dict[str, int], default_id: str | None, seen: set[str], result: CsvParseResult) -> None:
    def skip(reason: str, detail: str = "") -> None:
        result.issues.append(RowIssue(line, reason, detail))

    if len(cells) != len(header):
        return skip("열 개수가 머리글과 다릅니다", f"머리글 {len(header)}개, 이 줄 {len(cells)}개")
    if "video_id" in index:
        cell = cells[index["video_id"]].strip()
        if normalize_for_match(cell) in _TOTAL_LABELS:
            return skip("합계 행이라 건너뜀")
        if not VIDEO_ID_RE.match(cell):
            return skip("영상 ID 형식이 올바르지 않습니다", safe_cell(cell, 30))
        vid = cell
    else:
        vid = default_id  # type: ignore[assignment]  # _map_columns가 ID 열도 기본 ID도 없으면 이미 오류로 중단했다
        if result.data_rows > 1:
            return skip("영상 ID 열이 없는 파일은 한 줄만 가져올 수 있습니다(합계 줄)")
    if vid in seen:
        return skip("같은 영상이 파일에 중복되어 첫 줄만 사용합니다", vid)
    values: dict[str, int | float | None] = {}
    for fld, kind in (("impressions", "int"), ("ctr", "percent"), ("views", "int"), ("watch_minutes", "float"), ("watch_hours", "float")):
        if fld in index:
            value, why = parse_number(cells[index[fld]], kind)
            if why:
                return skip(f"{result.columns.get(fld, fld)} 값: {why}", safe_cell(cells[index[fld]], 30))
            values[fld] = value
    if "watch_hours" in values:  # 분 단위로 통일한다(DB 열이 watch_minutes)
        hours = values.pop("watch_hours")
        values["watch_minutes"] = None if hours is None else round(float(hours) * 60, 4)
    if all(values.get(f) is None for f in METRIC_FIELDS):
        return skip("지표 값이 하나도 없습니다")
    seen.add(vid)
    raw = {safe_cell(h, 60): safe_cell(c) for h, c in zip(header, cells)}
    result.rows.append(CsvRow(line, vid, values.get("impressions"), values.get("ctr"), values.get("views"), values.get("watch_minutes"), raw))  # type: ignore[arg-type]


def read_csv_file(path: Path | str, base_dir: Path, default_video_id: str | None = None) -> CsvParseResult:
    """파일을 읽어 파싱한다. 상대 경로는 프로젝트 폴더(base_dir) 기준. 위치 제한은 없다(사용자가 직접 지정한 읽기 전용 파일, 보통 다운로드 폴더)."""
    p = Path(path)
    p = p if p.is_absolute() else Path(base_dir) / p
    if p.suffix.lower() != ".csv":
        raise InputError(f"CSV 파일(.csv)이 아닙니다: {safe_cell(p.name, 60)}", "Studio에서 내보낸 .csv 파일을 지정하세요.")
    try:
        if not p.is_file():  # 폴더·장치·파이프는 읽지 않는다
            raise InputError(f"CSV 파일을 찾을 수 없습니다: {safe_cell(p.name, 60)}", "파일 경로(상대 경로는 프로젝트 폴더 기준)를 확인하세요.")
        size = p.stat().st_size
        if size > MAX_BYTES:
            raise InputError(f"CSV 파일이 너무 큽니다({size // 1024}KB > {MAX_BYTES // 1024}KB).", "필요한 기간·영상만 다시 내보내 크기를 줄이세요.")
        with p.open("rb") as fh:
            raw = fh.read(MAX_BYTES + 1)  # 파일이 읽는 도중 커져도 상한을 넘겨 읽지 않는다
    except OSError as exc:
        raise InputError("CSV 파일을 읽을 수 없습니다.", "파일 권한과 경로를 확인하세요.", cause=type(exc).__name__) from exc
    return parse_csv_bytes(raw, default_video_id)


def parse_day(value: str, label: str) -> str:
    """`YYYY-MM-DD`만 허용한다. 반환은 같은 형식의 문자열."""
    s = value.strip()
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s):
        try:
            return date.fromisoformat(s).isoformat()
        except ValueError:
            pass  # 2026-02-30 같은 없는 날짜
    raise InputError(f"{label} 날짜 형식이 올바르지 않습니다.", "YYYY-MM-DD 형식으로 입력하세요. 예: 2026-01-31")


def store_rows(conn: sqlite3.Connection, rows: list[CsvRow], *, phase: str, period_start: str | None, period_end: str | None, now: datetime) -> StoreResult:
    """검증된 행을 metrics_snapshots(source='csv')에 한 번의 트랜잭션으로 저장한다. 같은 내용을 다시 가져오면 중복 저장하지 않는다."""
    if phase not in PHASES:
        raise InputError(f"지표 단계 값이 올바르지 않습니다: {phase!r}", "before, after, periodic 중 하나를 쓰세요.")
    if (period_start is None) != (period_end is None):
        raise InputError("기간의 시작일과 종료일은 함께 지정해야 합니다.", "`--period-start`와 `--period-end`를 둘 다 쓰거나 둘 다 생략하세요.")
    if period_start is not None and period_end is not None and period_start > period_end:
        raise InputError("기간의 시작일이 종료일보다 늦습니다.", "기간을 확인하세요.")
    out = StoreResult()
    taken_at = utc_iso(now)
    try:
        with conn:
            for r in rows:
                dup = conn.execute(
                    "SELECT 1 FROM metrics_snapshots WHERE video_id = ? AND phase = ? AND source = 'csv' AND period_start IS ? AND period_end IS ? "
                    "AND impressions IS ? AND ctr IS ? AND views IS ? AND watch_minutes IS ? LIMIT 1",
                    (r.video_id, phase, period_start, period_end, r.impressions, r.ctr, r.views, r.watch_minutes),
                ).fetchone()
                if dup:
                    out.duplicates += 1
                    continue
                if conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (r.video_id,)).fetchone() is None:
                    out.unknown_videos += 1
                conn.execute(
                    "INSERT INTO metrics_snapshots (video_id, taken_at, phase, source, period_start, period_end, impressions, ctr, views, watch_minutes, raw_json) VALUES (?,?,?,'csv',?,?,?,?,?,?,?)",
                    (r.video_id, taken_at, phase, period_start, period_end, r.impressions, r.ctr, r.views, r.watch_minutes, json.dumps({"line": r.line, "cells": r.raw}, ensure_ascii=False)),
                )
                out.inserted += 1
    except sqlite3.Error as exc:
        raise DatabaseError("가져온 지표를 저장하지 못했습니다(일부만 저장되지 않고 전부 취소했습니다).", "data 폴더의 쓰기 권한과 디스크 공간을 확인하세요.", cause=type(exc).__name__) from exc
    return out
