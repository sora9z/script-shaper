from utils.openai_extract import (
    LineLabel, Classification, classify_lines, extract_dialogue_ai, ScriptPattern,
)


class _FakeCompletions:
    """chat.completions.parse 흉내: 넘어온 target id들을 canned rule로 라벨링."""
    def __init__(self, rule, drop_ids=None):
        self.rule = rule
        self.drop_ids = drop_ids or set()

    def parse(self, *, model, messages, response_format, **kwargs):
        if response_format is not Classification:
            # 패턴 분석 요청: 기본 fake는 지원 안 함 → analyze_pattern이 None 폴백
            raise RuntimeError("pattern analysis unsupported by this fake")
        user = messages[-1]["content"]
        labels = []
        for line in user.splitlines():
            if not line.startswith("[TARGET]"):
                continue
            # format: "[TARGET] <id>\t<text>"
            head, text = line[len("[TARGET] "):].split("\t", 1)
            gid = int(head)
            if gid in self.drop_ids:
                continue
            labels.append(self.rule(gid, text))
        parsed = Classification(labels=labels)

        class _Msg:  # noqa
            def __init__(self, p): self.parsed = p
        class _Choice:  # noqa
            def __init__(self, p): self.message = _Msg(p)
        class _Resp:  # noqa
            def __init__(self, p): self.choices = [_Choice(p)]
        return _Resp(parsed)


class _FakeClient:
    def __init__(self, rule, drop_ids=None):
        class _Chat:  # noqa
            def __init__(self, c): self.completions = c
        self.chat = _Chat(_FakeCompletions(rule, drop_ids))


def _rule_all_dialogue(gid, text):
    return LineLabel(id=gid, type="dialogue", speaker=None)


def test_classify_lines_fills_by_echoed_id():
    lines = [f"line {i}" for i in range(120)]
    labels = classify_lines("k", lines, _client=_FakeClient(_rule_all_dialogue))
    assert len(labels) == 120
    assert all(lab is not None and lab.id == i for i, lab in enumerate(labels))


def test_classify_lines_leaves_dropped_ids_none():
    lines = [f"line {i}" for i in range(60)]
    labels = classify_lines("k", lines, _client=_FakeClient(_rule_all_dialogue, drop_ids={3, 4}))
    assert labels[3] is None and labels[4] is None
    assert labels[0] is not None


def test_extract_dialogue_ai_falls_back_to_regex_for_none_ids():
    # id 0은 모델이 드롭 → regex 폴백. '안녕하세요.'는 '요' 어미로 대사 인식됨.
    lines = ["안녕하세요.", "은비        학교요?"]
    out = extract_dialogue_ai(
        lines, "x.docx", "k",
        _client=_FakeClient(_rule_all_dialogue, drop_ids={0}),
    )
    assert "안녕하세요." in out          # 폴백으로 살아남음
    assert "학교요?" in out


def test_extract_dialogue_ai_xlsx_bypass_calls_no_client():
    sentinel = object()  # client가 쓰이면 AttributeError로 터짐
    out = extract_dialogue_ai(["셀1 대사", "셀2 대사"], "data.xlsx", "k", _client=sentinel)
    assert out == "셀1 대사\n셀2 대사"


def test_fallback_strips_speaker_prefix_for_dropped_line():
    # 콜론형 화자명 대사를 모델이 드롭 → 폴백이 화자명을 제거해야 한다
    lines = ["민수:    안녕하세요."]
    out = extract_dialogue_ai(
        lines, "x.docx", "k",
        _client=_FakeClient(_rule_all_dialogue, drop_ids={0}),
    )
    assert out == "안녕하세요."


def test_xlsx_bypass_strips_speaker_and_directions_like_off_path():
    # .xlsx 도 OFF 경로처럼 화자명·지문을 제거해야 한다(분류기는 호출하지 않음)
    cells = ["민수: 안녕하세요", "소영   반가워 (웃음)"]
    out = extract_dialogue_ai(cells, "x.xlsx", "k")
    assert "민수" not in out and "소영" not in out   # 화자명 제거
    assert "(웃음)" not in out                        # 지문 제거
    assert "안녕하세요" in out and "반가워" in out


class _PatternAwareFake:
    """패턴 요청엔 ScriptPattern을, 분류 요청엔 라벨을 반환하고 프롬프트를 기록."""

    def __init__(self, pattern, rule):
        self.pattern = pattern
        self.rule = rule
        self.classify_calls = []  # (system_prompt, target_ids)
        outer = self

        class _Completions:
            def parse(self, *, model, messages, response_format, **kwargs):
                if response_format is ScriptPattern:
                    parsed = outer.pattern
                else:
                    system = messages[0]["content"]
                    labels, ids = [], []
                    for line in messages[-1]["content"].splitlines():
                        if not line.startswith("[TARGET]"):
                            continue
                        head, text = line[len("[TARGET] "):].split("\t", 1)
                        gid = int(head)
                        ids.append(gid)
                        labels.append(outer.rule(gid, text))
                    outer.classify_calls.append((system, ids))
                    parsed = Classification(labels=labels)

                class _Msg:  # noqa
                    def __init__(self, p): self.parsed = p
                class _Choice:  # noqa
                    def __init__(self, p): self.message = _Msg(p)
                class _Resp:  # noqa
                    def __init__(self, p): self.choices = [_Choice(p)]
                return _Resp(parsed)

        class _Chat:
            def __init__(self, c): self.completions = c
        self.chat = _Chat(_Completions())


def _speaker_doc(n_blocks=30, block=4):
    # "이름N    대사" 화자줄 + 연속줄 3개 = 4줄 블록 × 30 = 120줄
    lines = []
    for i in range(n_blocks):
        lines.append(f"이름{i}    대사{i}!")
        lines += [f"이어지는 대사 {i}-{j}" for j in range(block - 1)]
    return lines


_DOC_PATTERN = ScriptPattern(
    speaker_line_regex=r"^이름\d+\s{3,}",
    scene_header_regex=None,
    pattern_description="화자명 '이름N' 뒤 공백 3칸 이상",
    speaker_examples=["이름0    대사0!"],
)


def test_pattern_path_injects_prompt_and_aligns_first_chunk():
    lines = _speaker_doc()  # 120줄, 화자줄은 idx 0,4,8,...
    fake = _PatternAwareFake(_DOC_PATTERN, _rule_all_dialogue)
    out = extract_dialogue_ai(lines, "x.docx", "k", _client=fake)

    # 프롬프트 주입 확인
    system, ids = fake.classify_calls[0]
    assert "[이 문서의 확인된 패턴]" in system
    assert "이름0    대사0!" in system

    # 경계 정렬 확인: base=50 → idx50은 연속줄(50%4==2) → idx52(화자줄)까지 연장
    assert ids == list(range(0, 52))

    # 추출 결과가 여전히 원문 slice인지(무변형) 확인
    assert "대사0!" in out and "이어지는 대사 29-2" in out


def test_pattern_failure_falls_back_to_fixed_chunking():
    # 검증 탈락 regex(전부 매치) → 고정 50줄 청킹 + 일반 프롬프트
    bad = ScriptPattern(
        speaker_line_regex=r"^.*",
        pattern_description="d",
        speaker_examples=["x"],
    )
    lines = _speaker_doc()
    fake = _PatternAwareFake(bad, _rule_all_dialogue)
    extract_dialogue_ai(lines, "x.docx", "k", _client=fake)
    system, ids = fake.classify_calls[0]
    assert "[이 문서의 확인된 패턴]" not in system
    assert ids == list(range(0, 50))  # 현행 고정 50줄
