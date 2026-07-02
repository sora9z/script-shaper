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


# ---------- chunk_by_speaker_boundaries ----------

from utils.openai_extract import chunk_by_speaker_boundaries

_SPK = re.compile(r"^S\d+ ")


def test_chunks_align_to_speaker_boundary():
    # 4줄 블록: S{i}, 이어짐 3줄
    lines = []
    for i in range(10):
        lines.append(f"S{i} 대사")
        lines += [f"이어짐{i}a", f"이어짐{i}b", f"이어짐{i}c"]
    chunks = chunk_by_speaker_boundaries(lines, _SPK, base=10, extend=5)
    assert chunks[0] == (0, 12)  # idx10은 연속줄 → idx12(S3) 직전까지 연장
    for start, end in chunks[:-1]:
        assert _SPK.match(lines[end])  # 다음 청크는 항상 화자줄에서 시작


def test_chunks_cover_all_lines_without_overlap_or_gap():
    lines = [f"S{i // 4} x" if i % 4 == 0 else f"cont{i}" for i in range(103)]
    chunks = chunk_by_speaker_boundaries(lines, _SPK, base=10, extend=5)
    flat = [i for s, e in chunks for i in range(s, e)]
    assert flat == list(range(103))


def test_no_boundary_within_extend_keeps_base():
    lines = ["S0 시작"] + [f"cont{i}" for i in range(60)]  # 화자줄이 하나뿐
    chunks = chunk_by_speaker_boundaries(lines, _SPK, base=10, extend=5)
    assert chunks[0] == (0, 10)  # 연장 실패 → 현행처럼 base에서 절단


def test_boundary_exactly_at_base_needs_no_extension():
    lines = []
    for i in range(4):
        lines.append(f"S{i} 대사")
        lines += [f"c{i}{j}" for j in range(9)]  # 블록 10줄
    chunks = chunk_by_speaker_boundaries(lines, _SPK, base=10, extend=5)
    assert chunks == [(0, 10), (10, 20), (20, 30), (30, 40)]


def test_scene_header_is_also_boundary():
    scene = re.compile(r"^#\d+\.")
    lines = [f"cont{i}" for i in range(20)]
    lines[11] = "#2. 교정"
    chunks = chunk_by_speaker_boundaries(lines, _SPK, scene, base=10, extend=5)
    assert chunks[0] == (0, 11)


def test_boundary_at_exactly_extend_is_found():
    # 경계가 base+extend 지점에 정확히 있을 때도 찾아야 한다(포함 범위)
    lines = [f"cont{i}" for i in range(30)]
    lines[0] = "S0 시작"
    lines[15] = "S1 다음"  # base=10, extend=5 → base+extend=15
    chunks = chunk_by_speaker_boundaries(lines, _SPK, base=10, extend=5)
    assert chunks[0] == (0, 15)
