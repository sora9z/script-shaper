import re

from utils.openai_extract import (
    ScriptPattern,
    sample_windows,
)


# ---------- ScriptPattern ----------

def test_script_pattern_schema_defaults():
    p = ScriptPattern(
        speaker_line_regex=r"^[가-힣]+\s{3,}",
        pattern_description="화자명 뒤 3칸 이상 공백",
        speaker_examples=["은비    학교요?"],
    )
    assert p.scene_header_regex is None
    assert p.speaker_examples == ["은비    학교요?"]


# ---------- sample_windows ----------

def test_sample_windows_long_doc_three_windows():
    lines = [f"줄{i}" for i in range(300)]
    w = sample_windows(lines)
    assert len(w) == 120
    assert w[:40] == lines[:40]                       # 앞
    mid_start = (300 - 40) // 2
    assert w[40:80] == lines[mid_start:mid_start + 40]  # 중간
    assert w[80:] == lines[-40:]                      # 끝


def test_sample_windows_short_doc_returns_all_once():
    lines = [f"줄{i}" for i in range(50)]
    assert sample_windows(lines) == lines


def test_sample_windows_exact_boundary_returns_all():
    lines = [f"줄{i}" for i in range(120)]  # 정확히 3*40
    assert sample_windows(lines) == lines
