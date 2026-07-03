# Pattern-Aware Chunking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a once-per-document AI "pattern analysis" pass that learns the script's speaker-line format, then uses it to (1) align classification chunk boundaries to speaker lines and (2) inject the document's pattern into the classification prompt — improving extraction accuracy.

**Architecture:** New pure functions (`sample_windows`, `validate_pattern`, `chunk_by_speaker_boundaries`) plus one new API call (`analyze_pattern`, structured output `ScriptPattern`) in `utils/openai_extract.py`. `classify_lines` gains optional pattern parameters; `extract_dialogue_ai` orchestrates analyze→validate→classify. Any failure at any stage falls back to the exact current behavior (fixed 50-line chunks + generic prompt).

**Tech Stack:** Python 3.11, `openai` 2.x (`client.chat.completions.parse`), `pydantic` 2.x, pytest. Spec: `docs/superpowers/specs/2026-07-02-pattern-aware-chunking-design.md`.

## Global Constraints

- Dialogue text is never regenerated — the pattern pass produces labels/regex only; assembly still slices from source.
- AI-OFF path untouched; `.xlsx`/`.xls` bypass untouched (returns before pattern analysis).
- No `temperature` argument on any `gpt-5.4` call.
- Pattern-path failure ⇒ byte-identical to current behavior (fixed `CLASSIFY_CHUNK_LINES=50` chunks, generic `_SYSTEM_PROMPT`). Existing 24 tests must stay green.
- Validation bounds (verbatim from spec): regex length ≤ **200** chars; match ratio within **[0.05, 0.60]**; sampling **3 windows × 40 lines** (front/middle/end); boundary extension max **+30** lines.
- Run tests via `pipenv run python -m pytest` from repo root.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

## File Structure

- `utils/openai_extract.py` — all new code (schema, pure functions, API function, wiring). Kept in one module: cohesive with the existing classifier, and every piece shares its constants.
- `tests/test_pattern_analysis.py` — NEW: unit tests for `sample_windows`, `validate_pattern`, `chunk_by_speaker_boundaries`, `analyze_pattern`, `_pattern_prompt_block`.
- `tests/test_extract_orchestration.py` — MODIFIED: `_FakeCompletions` learns to dispatch on `response_format`; new integration tests for the pattern-aware path and its fallback.
- `CLAUDE.md` — one-sentence doc note (folded into final task).

---

### Task 1: `ScriptPattern` schema + `sample_windows`

**Files:**
- Modify: `utils/openai_extract.py`
- Test: `tests/test_pattern_analysis.py` (create)

**Interfaces:**
- Consumes: nothing new (pydantic `BaseModel`, `Optional` already imported in the module).
- Produces:
  - `class ScriptPattern(BaseModel)`: `speaker_line_regex: str`, `scene_header_regex: Optional[str] = None`, `pattern_description: str`, `speaker_examples: list[str]`
  - `sample_windows(lines: list[str], n_windows: int = 3, window: int = 40) -> list[str]`
  - Constants `SAMPLE_WINDOWS = 3`, `SAMPLE_WINDOW_LINES = 40`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pattern_analysis.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: collection ERROR — `ImportError: cannot import name 'ScriptPattern'`.

- [ ] **Step 3: Implement**

In `utils/openai_extract.py`, after the `Classification` class, add:

```python
SAMPLE_WINDOWS = 3
SAMPLE_WINDOW_LINES = 40


class ScriptPattern(BaseModel):
    """문서 1회 패턴 분석 결과 (structured output)."""
    speaker_line_regex: str            # 화자줄 판정 regex, ^ 앵커
    scene_header_regex: Optional[str] = None
    pattern_description: str           # 분류 프롬프트 주입용 한국어 설명
    speaker_examples: list[str]        # 샘플에서 그대로 복사한 화자줄 예시


def sample_windows(lines: list[str], n_windows: int = SAMPLE_WINDOWS,
                   window: int = SAMPLE_WINDOW_LINES) -> list[str]:
    """패턴 분석용 샘플: 앞/중간/끝 윈도우. 짧은 문서는 전체를 그대로 반환."""
    if len(lines) <= n_windows * window:
        return list(lines)
    mid_start = (len(lines) - window) // 2
    return lines[:window] + lines[mid_start:mid_start + window] + lines[-window:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: 4 passed.

- [ ] **Step 5: Full suite green, then commit**

Run: `pipenv run python -m pytest -q` → expected 28 passed (24 existing + 4).

```bash
git add utils/openai_extract.py tests/test_pattern_analysis.py
git commit -m "feat: add ScriptPattern schema and sample_windows for pattern analysis

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `validate_pattern`

**Files:**
- Modify: `utils/openai_extract.py` (add `import re` at top — the module does not import it yet)
- Test: `tests/test_pattern_analysis.py`

**Interfaces:**
- Consumes: `ScriptPattern` (Task 1).
- Produces:
  - `validate_pattern(pattern: ScriptPattern, lines: list[str]) -> tuple[Optional[re.Pattern], Optional[re.Pattern]]` — `(speaker_re, scene_re)`; `(None, None)` on any speaker-regex failure; scene regex failure discards scene only.
  - Constants `MAX_PATTERN_REGEX_LEN = 200`, `MATCH_RATIO_MIN = 0.05`, `MATCH_RATIO_MAX = 0.60`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pattern_analysis.py`:

```python
from utils.openai_extract import validate_pattern


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: ERROR — `ImportError: cannot import name 'validate_pattern'`.

- [ ] **Step 3: Implement**

Add `import re` to the top of `utils/openai_extract.py` (first import line). After `sample_windows`, add:

```python
MAX_PATTERN_REGEX_LEN = 200
MATCH_RATIO_MIN = 0.05
MATCH_RATIO_MAX = 0.60


def validate_pattern(pattern: ScriptPattern, lines: list[str]):
    """speaker regex를 컴파일·상식 검증. 반환 (speaker_re, scene_re); 실패 시 (None, None).

    - 길이 ≤ MAX_PATTERN_REGEX_LEN, 컴파일 가능해야 함
    - 전체 줄 대비 매치율이 [MATCH_RATIO_MIN, MATCH_RATIO_MAX] 여야 함(화자줄은 '일부'라는 상식)
    - scene regex는 실패해도 그것만 버림(전체 폴백 아님)
    """
    if not lines or not pattern.speaker_line_regex:
        return None, None
    rx = pattern.speaker_line_regex
    if len(rx) > MAX_PATTERN_REGEX_LEN:
        return None, None
    try:
        speaker_re = re.compile(rx)
    except re.error:
        return None, None
    ratio = sum(1 for ln in lines if speaker_re.match(ln)) / len(lines)
    if not (MATCH_RATIO_MIN <= ratio <= MATCH_RATIO_MAX):
        return None, None

    scene_re = None
    if pattern.scene_header_regex and len(pattern.scene_header_regex) <= MAX_PATTERN_REGEX_LEN:
        try:
            scene_re = re.compile(pattern.scene_header_regex)
        except re.error:
            scene_re = None
    return speaker_re, scene_re
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add utils/openai_extract.py tests/test_pattern_analysis.py
git commit -m "feat: validate LLM-produced speaker regex with sanity bounds

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `chunk_by_speaker_boundaries`

**Files:**
- Modify: `utils/openai_extract.py`
- Test: `tests/test_pattern_analysis.py`

**Interfaces:**
- Consumes: compiled `re.Pattern` objects from Task 2.
- Produces:
  - `chunk_by_speaker_boundaries(lines: list[str], speaker_re, scene_re=None, base=CLASSIFY_CHUNK_LINES, extend=CHUNK_EXTEND_LINES) -> list[tuple[int, int]]` — `[start, end)` ranges covering all lines, no overlap; each range's end aligned to the next speaker/scene line when found within `extend` lines past `base`.
  - Constant `CHUNK_EXTEND_LINES = 30`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pattern_analysis.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: ERROR — `ImportError: cannot import name 'chunk_by_speaker_boundaries'`.

- [ ] **Step 3: Implement**

Add after `validate_pattern` (constant next to the other CLASSIFY constants is fine too):

```python
CHUNK_EXTEND_LINES = 30


def chunk_by_speaker_boundaries(lines, speaker_re, scene_re=None,
                                base=CLASSIFY_CHUNK_LINES,
                                extend=CHUNK_EXTEND_LINES):
    """화자줄/씬헤더 '직전'으로 끝을 정렬한 [start, end) 청크 목록.

    base 지점이 이미 경계면 그대로 절단, 아니면 최대 extend줄 안에서
    다음 경계를 찾아 연장. 경계가 없으면 base 그대로(현행과 동일).
    """
    def _is_boundary(ln):
        return bool(speaker_re.match(ln) or (scene_re and scene_re.match(ln)))

    n = len(lines)
    chunks = []
    start = 0
    while start < n:
        end = min(start + base, n)
        if end < n and not _is_boundary(lines[end]):
            for j in range(end + 1, min(end + extend, n)):
                if _is_boundary(lines[j]):
                    end = j
                    break
        chunks.append((start, end))
        start = end
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add utils/openai_extract.py tests/test_pattern_analysis.py
git commit -m "feat: speaker-boundary-aligned chunking with extension cap

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `analyze_pattern` + `_pattern_prompt_block`

**Files:**
- Modify: `utils/openai_extract.py`
- Test: `tests/test_pattern_analysis.py`

**Interfaces:**
- Consumes: `ScriptPattern`, `sample_windows` (Task 1); `OpenAI`, `CLASSIFY_MODEL` (existing).
- Produces:
  - `analyze_pattern(api_key, lines, model=CLASSIFY_MODEL, *, _client=None) -> Optional[ScriptPattern]` — one structured-output call on the sampled windows; `None` on ANY failure (exception, or parsed object is not a `ScriptPattern`).
  - `_pattern_prompt_block(pattern: ScriptPattern) -> str` — the Korean prompt block injected into the classifier system prompt.
  - `_PATTERN_SYSTEM_PROMPT` constant.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pattern_analysis.py`:

```python
from utils.openai_extract import analyze_pattern, _pattern_prompt_block


class _PatternFakeCompletions:
    def __init__(self, result=None, raise_exc=False):
        self.result = result
        self.raise_exc = raise_exc
        self.calls = []

    def parse(self, *, model, messages, response_format, **kwargs):
        self.calls.append({"messages": messages, "response_format": response_format})
        if self.raise_exc:
            raise RuntimeError("boom")

        class _Msg:
            def __init__(self, p): self.parsed = p
        class _Choice:
            def __init__(self, p): self.message = _Msg(p)
        class _Resp:
            def __init__(self, p): self.choices = [_Choice(p)]
        return _Resp(self.result)


class _PatternFakeClient:
    def __init__(self, result=None, raise_exc=False):
        self.completions = _PatternFakeCompletions(result, raise_exc)

        class _Chat:
            def __init__(self, c): self.completions = c
        self.chat = _Chat(self.completions)


_GOOD = ScriptPattern(
    speaker_line_regex=r"^[가-힣A-Za-z0-9/]+\s{3,}",
    scene_header_regex=r"^#\d+\.",
    pattern_description="화자명 뒤 공백 3칸 이상 후 대사",
    speaker_examples=["은비    학교요?", "수미/경진    짠!"],
)


def test_analyze_pattern_returns_parsed_pattern():
    fake = _PatternFakeClient(result=_GOOD)
    p = analyze_pattern("k", ["줄1", "줄2"], _client=fake)
    assert p is _GOOD
    assert fake.completions.calls[0]["response_format"] is ScriptPattern


def test_analyze_pattern_none_on_exception():
    assert analyze_pattern("k", ["줄"], _client=_PatternFakeClient(raise_exc=True)) is None


def test_analyze_pattern_none_on_wrong_parsed_type():
    fake = _PatternFakeClient(result="문자열임")  # ScriptPattern 아님
    assert analyze_pattern("k", ["줄"], _client=fake) is None


def test_analyze_pattern_sends_sampled_lines():
    lines = [f"줄{i}" for i in range(300)]
    fake = _PatternFakeClient(result=_GOOD)
    analyze_pattern("k", lines, _client=fake)
    user_msg = fake.completions.calls[0]["messages"][-1]["content"]
    assert "줄0" in user_msg and "줄299" in user_msg   # 앞/끝 윈도우 포함
    assert "줄45" not in user_msg                      # 윈도우 밖(45는 40~130 사이 아님) 제외


def test_pattern_prompt_block_contents():
    block = _pattern_prompt_block(_GOOD)
    assert "화자명 뒤 공백 3칸 이상 후 대사" in block
    assert "수미/경진    짠!" in block
    assert _GOOD.speaker_line_regex in block
    assert "연속 대사" in block
```

Note on `test_analyze_pattern_sends_sampled_lines`: for 300 lines the windows are `[0:40]`, `[130:170]`, `[260:300]` — `줄45` is outside all three.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: ERROR — `ImportError: cannot import name 'analyze_pattern'`.

- [ ] **Step 3: Implement**

Add after `chunk_by_speaker_boundaries`:

```python
_PATTERN_SYSTEM_PROMPT = """너는 한국어 방송 대본의 '표기 형식'을 분석하는 분석기다.
아래 대본 샘플을 보고, 이 문서에서 '화자줄'(등장인물 대사가 시작되는 줄)의 형식 패턴을 찾아라.

반환 규칙:
- speaker_line_regex: 화자줄만 매치하는 Python regex. 반드시 '^'로 시작(줄 앞 앵커).
  화자명에는 '/'나 숫자가 올 수 있고, 이름 뒤에 (E)/(N)/(O.L) 같은 표기가 붙을 수 있다.
  지문·씬헤더 줄은 매치하면 안 된다. 200자 이내로 작성해라.
- scene_header_regex: 씬 헤더 줄의 regex('^' 앵커). 씬 헤더가 없으면 null.
- pattern_description: 화자줄/지문/씬헤더를 구분하는 방법을 2~3문장의 한국어로.
- speaker_examples: 샘플에 실제로 존재하는 화자줄 2~5개를 그대로 복사해라."""


def analyze_pattern(api_key, lines, model=CLASSIFY_MODEL, *, _client=None):
    """문서 1회 패턴 분석. 어떤 실패든 None(→ 현행 방식으로 폴백)."""
    client = _client if _client is not None else OpenAI(api_key=api_key)
    sample = "\n".join(sample_windows(lines))
    try:
        resp = client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": _PATTERN_SYSTEM_PROMPT},
                {"role": "user", "content": sample},
            ],
            response_format=ScriptPattern,
        )
        parsed = resp.choices[0].message.parsed
        return parsed if isinstance(parsed, ScriptPattern) else None
    except Exception as e:
        print(f"패턴 분석 실패(현행 방식으로 진행): {e}")
        return None


def _pattern_prompt_block(pattern: ScriptPattern) -> str:
    examples = "\n".join(f"  - {ex}" for ex in pattern.speaker_examples[:5])
    return (
        "\n\n[이 문서의 확인된 패턴]\n"
        f"- 화자줄 형식: {pattern.pattern_description}\n"
        f"- 화자줄 예시:\n{examples}\n"
        f"- 참고 regex: {pattern.speaker_line_regex}\n"
        "- 화자줄 형식이 아닌데 대사로 판단되는 줄은 앞 화자의 '연속 대사'다 (speaker=null)."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pipenv run python -m pytest tests/test_pattern_analysis.py -q`
Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add utils/openai_extract.py tests/test_pattern_analysis.py
git commit -m "feat: one-shot document pattern analysis and prompt block builder

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Wire pattern into `classify_lines` / `extract_dialogue_ai`

**Files:**
- Modify: `utils/openai_extract.py` (`_classify_chunk`, `classify_lines`, `extract_dialogue_ai`)
- Modify: `tests/test_extract_orchestration.py` (`_FakeCompletions` dispatch + new tests)

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces (signature changes later callers rely on — `main.py`/`convert_cli.py` call `extract_dialogue_ai(text_list, file_path, api_key)` positionally, which must keep working unchanged):
  - `_classify_chunk(client, model, target, context, system_prompt=_SYSTEM_PROMPT)`
  - `classify_lines(api_key, lines, model=CLASSIFY_MODEL, *, _client=None, pattern=None, speaker_re=None, scene_re=None) -> list[Optional[LineLabel]]`
  - `extract_dialogue_ai(text_list, file_path, api_key, model=CLASSIFY_MODEL, *, _client=None) -> str` (signature unchanged; now runs analyze→validate→classify internally)

- [ ] **Step 1: Update the fake + write failing tests**

In `tests/test_extract_orchestration.py`, add the import at top:

```python
from utils.openai_extract import ScriptPattern
```

Replace the body of `_FakeCompletions.parse` so it dispatches on `response_format` (pattern requests raise by default → existing tests exercise the fallback path unchanged):

```python
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
```

Then append a pattern-capable fake and the new tests:

```python
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
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `pipenv run python -m pytest tests/test_extract_orchestration.py -q`
Expected: `test_pattern_path_injects_prompt_and_aligns_first_chunk` FAILS (prompt lacks the pattern block, first chunk is 50 not 52) — this is the RED that drives Step 3. `test_pattern_failure_falls_back_to_fixed_chunking` passes trivially before wiring (it is a regression guard that becomes meaningful after Step 3). Pre-existing tests in the file still pass.

- [ ] **Step 3: Implement the wiring**

In `utils/openai_extract.py`:

(a) `_classify_chunk` — add `system_prompt` parameter:

```python
def _classify_chunk(client, model, target, context, system_prompt=_SYSTEM_PROMPT):
    resp = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _format_prompt(target, context)},
        ],
        response_format=Classification,
    )
    return resp.choices[0].message.parsed.labels
```

(b) `classify_lines` — optional pattern params; boundary chunking + prompt injection when present:

```python
def classify_lines(api_key, lines, model=CLASSIFY_MODEL, *, _client=None,
                   pattern=None, speaker_re=None, scene_re=None):
    client = _client if _client is not None else OpenAI(api_key=api_key)
    n = len(lines)
    labels = [None] * n

    # 패턴이 검증된 경우: 화자 경계 정렬 청킹 + 프롬프트 주입. 아니면 현행 고정 청킹.
    system_prompt = _SYSTEM_PROMPT
    if pattern is not None and speaker_re is not None:
        system_prompt = _SYSTEM_PROMPT + _pattern_prompt_block(pattern)
        ranges = chunk_by_speaker_boundaries(lines, speaker_re, scene_re)
    else:
        ranges = []
        start = 0
        while start < n:
            ranges.append((start, min(start + CLASSIFY_CHUNK_LINES, n)))
            start = ranges[-1][1]

    chunks = []
    for start, end in ranges:
        ctx_start = max(0, start - CONTEXT_LINES)
        context = [(i, lines[i]) for i in range(ctx_start, start)]
        target = [(i, lines[i]) for i in range(start, end)]
        chunks.append((target, context))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_to_ids = {
            ex.submit(_classify_chunk, client, model, target, context, system_prompt):
                {gid for gid, _ in target}
            for target, context in chunks
        }
        for fut in as_completed(future_to_ids):
            valid_ids = future_to_ids[fut]
            try:
                for lab in fut.result():
                    if lab.id in valid_ids:
                        labels[lab.id] = lab
            except Exception as e:  # 청크 실패 → 해당 id들은 None으로 남겨 폴백
                print(f"청크 분류 실패({min(valid_ids)}~{max(valid_ids)}): {e}")
    return labels
```

(c) `extract_dialogue_ai` — insert the pattern pass between the xlsx branch and classification (the rest of the function body is unchanged):

```python
    # 문서 1회 패턴 분석 → 검증 실패 시 None(현행 경로)
    pattern = analyze_pattern(api_key, text_list, model, _client=_client)
    speaker_re = scene_re = None
    if pattern is not None:
        speaker_re, scene_re = validate_pattern(pattern, text_list)
        if speaker_re is None:
            pattern = None

    labels = classify_lines(api_key, text_list, model, _client=_client,
                            pattern=pattern, speaker_re=speaker_re, scene_re=scene_re)
```

- [ ] **Step 4: Run the full suite**

Run: `pipenv run python -m pytest -q`
Expected: 30 passed (28 + 2 new; every pre-existing orchestration test still passes because the default `_FakeClient` raises on the pattern request and `analyze_pattern` swallows it → identical current behavior).

- [ ] **Step 5: Commit**

```bash
git add utils/openai_extract.py tests/test_extract_orchestration.py
git commit -m "feat: pattern-aware chunk boundaries and prompt injection in classifier

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Docs + final verification

**Files:**
- Modify: `CLAUDE.md` (AI-ON paragraph in "Dialogue detection" section)

- [ ] **Step 1: Update CLAUDE.md**

In the paragraph beginning `When "AI 사용" is ON,` append this sentence at the end:

```markdown
Before classification, a once-per-document pattern pass (`analyze_pattern` → `validate_pattern`) learns the script's speaker-line regex, which aligns chunk boundaries to speaker lines (`chunk_by_speaker_boundaries`) and injects the document's format into the classifier prompt; any failure in that pass falls back to fixed 50-line chunks and the generic prompt.
```

- [ ] **Step 2: Full suite green**

Run: `pipenv run python -m pytest -q`
Expected: 30 passed.

- [ ] **Step 3: AI-OFF regression sanity (no network)**

Run: `pipenv run python -c "
import sys; sys.path.insert(0, '.')
from utils.import_file_to_text import import_file_to_text
from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue
from utils.data_processing import data_processing
SRC = 'issue/20260630/후아유 방송 01.docx'
t = import_file_to_text(SRC)
d = data_processing('\n'.join(extract_speaker_and_dialogue(t, SRC)))
print('lines:', len([l for l in d.split('\n') if l.strip()]))
"`
Expected: `lines: 675` (AI-OFF path untouched). Skip if the fixture docx is absent.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: describe pattern-aware chunking pass in CLAUDE.md

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** schema/sampling → Task 1; validation bounds (200 chars, 5–60%) → Task 2; boundary chunking (+30 cap, keep-base fallback) → Task 3; analysis call + prompt block → Task 4; wiring + fallback floor + xlsx untouched → Task 5; docs → Task 6. Live gpt-5.4 quality is runtime verification, outside this plan (needs user's key).
- **Placeholders:** none — all steps carry complete code and exact commands.
- **Type consistency:** `ScriptPattern` fields, `validate_pattern` returning `(speaker_re, scene_re)`, `chunk_by_speaker_boundaries(lines, speaker_re, scene_re, base, extend)`, and `classify_lines(..., pattern, speaker_re, scene_re)` are used with identical names/order in Tasks 2→5. `extract_dialogue_ai`'s public signature is unchanged, so `main.py`/`convert_cli.py` need no edits.
- **Arithmetic checks:** window math for 300 lines (mid 130–170), first-chunk alignment for the 4-line-block doc (50→52), corpus match ratio 0.2 — all verified by hand.
