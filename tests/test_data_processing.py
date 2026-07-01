from utils.data_processing import remove_inline_directions, data_processing


def test_removes_balanced_parentheses_direction():
    assert remove_inline_directions("안녕(웃음) 반가워") == "안녕 반가워"


def test_removes_balanced_bracket_direction():
    assert remove_inline_directions("[효과음] 문이 열린다") == " 문이 열린다"


def test_removes_trailing_unclosed_parenthesis_to_eol():
    assert remove_inline_directions("대사 시작 (미완성 괄호") == "대사 시작 "


def test_removes_unclosed_parenthesis_per_line_only():
    assert remove_inline_directions("첫줄 (열림\n둘째줄") == "첫줄 \n둘째줄"


def test_data_processing_still_strips_speaker_and_directions():
    # 화자명(콜론) 제거 + 괄호 지문 제거가 기존대로 동작
    assert data_processing("은비: (웃음) 안녕") == " 안녕"
