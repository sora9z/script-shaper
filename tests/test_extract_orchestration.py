from utils.openai_extract import (
    LineLabel, Classification, classify_lines, extract_dialogue_ai,
)


class _FakeCompletions:
    """chat.completions.parse 흉내: 넘어온 target id들을 canned rule로 라벨링."""
    def __init__(self, rule, drop_ids=None):
        self.rule = rule
        self.drop_ids = drop_ids or set()

    def parse(self, *, model, messages, response_format, **kwargs):
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
