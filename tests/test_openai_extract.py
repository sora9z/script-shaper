import os
import pytest

from utils.openai_extract import (
    LineLabel,
    remove_speaker_prefix,
    assemble_dialogue,
)
from utils.file_reader_list import read_file

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "issue", "20260630", "후아유 방송 01.docx"
)


# ---------- remove_speaker_prefix ----------

def test_strips_plain_speaker_with_space_gap():
    assert remove_speaker_prefix("은비        학교요? 가기 싫은데", "은비") == "학교요? 가기 싫은데"


def test_strips_speaker_with_slash_and_digits():
    assert remove_speaker_prefix("가해학생1/2    빠밤!", "가해학생1/2") == "빠밤!"


def test_keeps_annotation_after_slash_speaker_for_later_bracket_removal():
    # (E)가 화자와 대사 사이 → 이름만 잘라내고 (E)는 남겨 뒤에서 제거
    assert (
        remove_speaker_prefix("수미/경진(E)    생일 축하 합니다!", "수미/경진")
        == "(E)    생일 축하 합니다!"
    )


def test_noop_when_speaker_not_a_prefix():
    assert remove_speaker_prefix("놔, 이거 놔!", "소영") == "놔, 이거 놔!"


def test_noop_when_speaker_too_long():
    line = "가나다라마바사아자차카타파 대사"
    assert remove_speaker_prefix(line, "가나다라마바사아자차카타파") == line


def test_noop_when_no_token_boundary_after_name():
    # 이름 바로 뒤에 경계(공백/괄호)가 없으면 대사를 침범하지 않도록 no-op
    assert remove_speaker_prefix("수미짠!", "수미") == "수미짠!"


def test_noop_when_speaker_none():
    assert remove_speaker_prefix("아무 대사", None) == "아무 대사"


def test_strips_colon_form_speaker():
    # 화자명: 대사 형식 — 콜론 구분자도 잘라내야 한다
    assert remove_speaker_prefix("민수: 안녕하세요", "민수") == "안녕하세요"


def test_colon_fix_still_preserves_annotation_paren():
    # 콜론 처리가 (E) 괄호 표기는 건드리지 않아야 한다(뒤에서 제거)
    assert (
        remove_speaker_prefix("수미/경진(E)    생일 축하 합니다!", "수미/경진")
        == "(E)    생일 축하 합니다!"
    )


# ---------- assemble_dialogue ----------

def test_assemble_fixes_all_three_bugs():
    lines = [
        "수미/경진(E)    생일 축하 합니다! 생일 축하 합니다!",  # 0 대사 (#3: 유지돼야)
        "서랍에서 통장 두 개 꺼내 보인다. 뿌듯하다.",           # 1 지문 (#1: 제거돼야)
        "수미/경진    짠!",                                    # 2 대사, 화자명 제거 (#2)
        "#2. 통영누리여고 교정. 아침",                         # 3 씬헤더 (제거)
        "가해학생1/2    빠밤!",                                # 4 대사, 화자명 제거 (#2)
    ]
    labels = [
        LineLabel(id=0, type="dialogue", speaker="수미/경진"),
        LineLabel(id=1, type="narration", speaker=None),
        LineLabel(id=2, type="dialogue", speaker="수미/경진"),
        LineLabel(id=3, type="scene", speaker=None),
        LineLabel(id=4, type="dialogue", speaker="가해학생1/2"),
    ]
    assert (
        assemble_dialogue(lines, labels)
        == "생일 축하 합니다! 생일 축하 합니다!\n짠!\n빠밤!"
    )


def test_assemble_keeps_continuation_line_with_null_speaker():
    lines = ["은비        학교요?", "만약에 학교를 영영 못 다니게 된다면..."]
    labels = [
        LineLabel(id=0, type="dialogue", speaker="은비"),
        LineLabel(id=1, type="dialogue", speaker=None),
    ]
    assert assemble_dialogue(lines, labels) == "학교요?\n만약에 학교를 영영 못 다니게 된다면..."


def test_assemble_drops_unlabeled_lines():
    lines = ["대사요", "미분류"]
    labels = [LineLabel(id=0, type="dialogue", speaker=None)]  # id 1 없음
    assert assemble_dialogue(lines, labels) == "대사요"


# ---------- fixture anchors (실제 docx 라인 형태 고정) ----------

@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="원본 대본 fixture 없음(로컬 전용)")
def test_fixture_contains_expected_raw_line_shapes():
    lines = read_file(FIXTURE)
    assert "수미/경진(E)    생일 축하 합니다! 생일 축하 합니다!" in lines  # #3 대상
    assert "서랍에서 통장 두 개 꺼내 보인다. 뿌듯하다." in lines            # #1 대상
    assert "가해학생1/2    빠밤!" in lines                                # #2 대상
