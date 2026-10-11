"""테스트 번호 점검(144): TC-WB-001부터 빠짐·중복 없이 이어진다."""
from __future__ import annotations

import re
from pathlib import Path


def test_tc_wb_144_numbers_are_contiguous_and_unique():
    found = []
    for path in Path(__file__).parent.glob("test_*.py"):
        found += [int(n) for n in re.findall(r"^def test_tc_wb_(\d{3})_", path.read_text(encoding="utf-8"), re.M)]
    assert sorted(found) == list(range(1, len(found) + 1)), "TC-WB 번호가 연속이 아니거나 중복입니다"
