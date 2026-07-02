import re

from utils.openai_extract import (
    ScriptPattern,
    sample_windows,
    validate_pattern,
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


# ---------- validate_pattern ----------


def _mk(regex, scene=None):
    return ScriptPattern(
        speaker_line_regex=regex,
        scene_header_regex=scene,
        pattern_description="d",
        speaker_examples=["x"],
    )


_CORPUS = (["이름1    대사"] * 2 + ["지문 설명 줄"] * 8) * 5  # 화자줄 비율 0.2


def test_validate_pattern_accepts_sane_regex():
    speaker_re, scene_re = validate_pattern(_mk(r"^이름\d+\s{3,}"), _CORPUS)
    assert speaker_re is not None and scene_re is None
    assert speaker_re.match("이름1    대사")


def test_validate_pattern_rejects_uncompilable():
    assert validate_pattern(_mk(r"["), _CORPUS) == (None, None)


def test_validate_pattern_rejects_overmatching():
    assert validate_pattern(_mk(r"^.*"), _CORPUS) == (None, None)  # 비율 1.0 > 0.60


def test_validate_pattern_rejects_no_match():
    assert validate_pattern(_mk(r"^ZZZ"), _CORPUS) == (None, None)  # 비율 0 < 0.05


def test_validate_pattern_rejects_overlong_regex():
    assert validate_pattern(_mk(r"^" + r"a?" * 150), _CORPUS) == (None, None)


def test_validate_pattern_scene_failure_keeps_speaker():
    speaker_re, scene_re = validate_pattern(
        _mk(r"^이름\d+\s{3,}", scene=r"["), _CORPUS
    )
    assert speaker_re is not None and scene_re is None


def test_validate_pattern_valid_scene_regex():
    speaker_re, scene_re = validate_pattern(
        _mk(r"^이름\d+\s{3,}", scene=r"^#\d+\."), _CORPUS
    )
    assert speaker_re is not None and scene_re is not None
    assert scene_re.match("#3. 교정. 아침")
