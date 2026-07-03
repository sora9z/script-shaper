# AI Dialogue Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the buggy rule-based dialogue extraction with an AI-judgment pass (classify each line + locate speaker name) so 지문 is dropped, speaker names are stripped, and `(E)`-annotated dialogue is no longer lost — while dialogue text is only ever sliced from the source, never regenerated.

**Architecture:** When "AI 사용" is ON, `read_file` output is sent to an OpenAI structured-output classifier that labels each line `dialogue|narration|scene|other` and returns the bare speaker name; deterministic code keeps only dialogue lines, slices off the speaker prefix, and strips bracketed inline directions. The existing 20-char split remains a separate downstream step. When AI is OFF, the original `extract_speaker_and_dialogue` + `data_processing` path runs unchanged (no key needed).

**Tech Stack:** Python 3.11, `openai` 2.x (`client.chat.completions.parse` structured outputs), `pydantic` 2.x, `python-docx`, pytest.

## Global Constraints

- **Dialogue text must never be altered.** The model returns labels only; dialogue characters are always a substring sliced from the original line (four independent guards in `remove_speaker_prefix`).
- **AI-OFF path stays byte-for-byte identical** to today: it must call only `extract_speaker_and_dialogue` + `data_processing`, never the new module, and never touch the network.
- Classification model: `gpt-5.4`. Structured output via `client.chat.completions.parse(response_format=Classification)`.
- Do **not** pass `temperature` to `gpt-5.4` (reasoning-family models may reject it); rely on the strict schema for output shape.
- OpenAI SDK floor: `openai = ">=2.0"` in `Pipfile` (env currently resolves to 2.44.0).
- Speaker names may contain `/` and digits (`수미/경진`, `가해학생1/2`) and must be preserved by the classifier and matched verbatim by the slicer.
- Run tests with `pipenv run python -m pytest` from repo root (puts repo root on `sys.path`).

---

## File Structure

- `utils/data_processing.py` — **[DONE]** adds `remove_inline_directions(text)` helper (bracket/inline-direction removal), reused by both `data_processing` and the AI path.
- `utils/openai_extract.py` — **NEW** — schema (`LineLabel`, `Classification`), pure functions (`remove_speaker_prefix`, `assemble_dialogue`), API functions (`classify_lines`, `extract_dialogue_ai`).
- `utils/openai.py` — split model `gpt-4o` → `gpt-5.4` (no structural change).
- `main.py` — `FileSelector.convert_file` branches on `use_ai`; loads key once; AI path uses `extract_dialogue_ai` then existing 20-char split.
- `convert_cli.py` — **NEW** — headless conversion for debugging/verification.
- `Pipfile` — pin `openai = ">=2.0"`.
- `tests/test_data_processing.py` — **[DONE]** helper + `data_processing` regression.
- `tests/test_openai_extract.py` — **[DONE, RED]** pure-function + fixture tests (awaiting GREEN in Task 2).
- `tests/test_extract_orchestration.py` — **NEW** — chunking/reconcile/fallback/xlsx with a fake client.
- `README.md`, `CLAUDE.md` — document AI-ON classification path + local run command.

---

### Task 1: Extract `remove_inline_directions` helper — ✅ DONE

**Files:** Modify `utils/data_processing.py`; Test `tests/test_data_processing.py`.

Completed in this session: the bracket/inline-direction block was factored into `remove_inline_directions(text) -> str`, and `data_processing` now calls it. 5 tests pass. No further action; listed for record.

---

### Task 2: Pure functions + schema in `utils/openai_extract.py`

**Files:**
- Create: `utils/openai_extract.py`
- Test: `tests/test_openai_extract.py` (already written, currently RED — module missing)

**Interfaces:**
- Consumes: `remove_inline_directions` from `utils/data_processing.py`.
- Produces:
  - `class LineLabel(BaseModel)`: `id:int`, `type:Literal["dialogue","narration","scene","other"]`, `speaker:Optional[str]=None`
  - `class Classification(BaseModel)`: `labels:list[LineLabel]`
  - `remove_speaker_prefix(line:str, speaker:Optional[str]) -> str`
  - `assemble_dialogue(lines:list[str], labels:list[LineLabel]) -> str`

- [ ] **Step 1: Confirm the failing tests exist and fail**

Run: `pipenv run python -m pytest tests/test_openai_extract.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'utils.openai_extract'`

- [ ] **Step 2: Create the module with schema + pure functions**

Create `utils/openai_extract.py` (only the parts needed for Task 2; API functions come in Task 3):

```python
from typing import Literal, Optional

from pydantic import BaseModel

from utils.data_processing import remove_inline_directions

MAX_SPEAKER_LEN = 12
_BOUNDARY = set(" \t([{")


class LineLabel(BaseModel):
    id: int
    type: Literal["dialogue", "narration", "scene", "other"]
    speaker: Optional[str] = None


class Classification(BaseModel):
    labels: list[LineLabel]


def remove_speaker_prefix(line: str, speaker: Optional[str]) -> str:
    """원문 line 앞의 화자명 토큰만 잘라낸다. 항상 원문이거나 우측 부분문자열을 반환."""
    if not speaker:
        return line
    sp = speaker.strip()
    if not sp or len(sp) > MAX_SPEAKER_LEN:
        return line                       # 가드: 비현실적 화자
    if not line.startswith(sp):
        return line                       # 가드: prefix 아님
    rest = line[len(sp):]
    if rest and rest[0] not in _BOUNDARY:
        return line                       # 가드: 토큰 경계 없음 → 대사 침범 방지
    return rest.lstrip()


def assemble_dialogue(lines: list[str], labels: list[LineLabel]) -> str:
    """dialogue 라인만 남기고 화자명·지문을 제거해 한 줄씩 이어 붙인다."""
    by_id = {lab.id: lab for lab in labels}
    kept = []
    for i, line in enumerate(lines):
        lab = by_id.get(i)
        if lab is None or lab.type != "dialogue":
            continue
        core = remove_speaker_prefix(line, lab.speaker)
        if not (core and core in line):
            core = line                   # 부분문자열 가드 실패 → 원문 유지(방어)
        kept.append(core)
    text = remove_inline_directions("\n".join(kept))
    return "\n".join(seg.strip() for seg in text.split("\n") if seg.strip())
```

- [ ] **Step 3: Run the tests to verify GREEN**

Run: `pipenv run python -m pytest tests/test_openai_extract.py -q`
Expected: PASS (10 tests) — including `test_assemble_fixes_all_three_bugs`, `test_assemble_keeps_continuation_line_with_null_speaker`, and the fixture anchor test.

- [ ] **Step 4: Run the full suite**

Run: `pipenv run python -m pytest -q`
Expected: PASS (Task 1 + Task 2 = 15 tests).

- [ ] **Step 5: Commit**

```bash
git add utils/openai_extract.py tests/test_openai_extract.py
git commit -m "feat: add AI-extraction pure functions (speaker slice + assembly)"
```

---

### Task 3: `classify_lines` + `extract_dialogue_ai` (chunk, parallel, reconcile, fallback, xlsx)

**Files:**
- Modify: `utils/openai_extract.py`
- Test: `tests/test_extract_orchestration.py` (create)

**Interfaces:**
- Consumes: `LineLabel`, `Classification`, `assemble_dialogue` (Task 2); `extract_speaker_and_dialogue` from `utils/extract_speaker_and_dialogue.py`; `OpenAI` from `openai`.
- Produces:
  - `classify_lines(api_key:str, lines:list[str], model:str="gpt-5.4", *, _client=None) -> list[Optional[LineLabel]]` (length == len(lines); `None` for any id the model dropped or a failed chunk)
  - `extract_dialogue_ai(text_list:list[str], file_path:str, api_key:str, model:str="gpt-5.4", *, _client=None) -> str`
  - Constants: `CLASSIFY_MODEL="gpt-5.4"`, `CLASSIFY_CHUNK_LINES=50`, `CONTEXT_LINES=5`, `MAX_WORKERS=5`

- [ ] **Step 1: Write failing tests with a fake client (no network)**

Create `tests/test_extract_orchestration.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pipenv run python -m pytest tests/test_extract_orchestration.py -q`
Expected: ERROR — `cannot import name 'classify_lines'` (functions not yet defined).

- [ ] **Step 3: Implement the API functions**

Append to `utils/openai_extract.py` (add imports at top of file: `from concurrent.futures import ThreadPoolExecutor, as_completed`, `from openai import OpenAI`, `from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue`):

```python
CLASSIFY_MODEL = "gpt-5.4"
CLASSIFY_CHUNK_LINES = 50
CONTEXT_LINES = 5
MAX_WORKERS = 5

_SYSTEM_PROMPT = """너는 한국어 방송 대본에서 각 줄의 역할을 분류하는 분석기다.
각 줄을 문장 끝 어미가 아니라 '역할'로 분류해라:
- dialogue: 등장인물이 말하는 대사. 문장이 '~다'나 ','로 끝나도 인물의 발화면 dialogue다.
- narration: 3인칭 지문(행동·카메라·장면 묘사). '보인다', '간다', '퍼진다'처럼 '~다'로 끝나도 지문이면 narration이다.
- scene: 씬 헤더. 예) '#1. 사랑의 집', '#2. 교정. 아침'.
- other: 제목·머리말 등 그 외. 예) '<제1회>', '#타이틀 < 후아유 >'.

speaker 규칙:
- dialogue인데 줄 맨 앞에 화자명이 있으면, 공백/괄호 앞의 '순수 이름 토큰'만 speaker로 반환한다.
- (E)/(N)/(O.L)/(F) 같은 표기와 인라인 지문 괄호는 speaker에 넣지 않는다.
- 이름에 '/'나 숫자가 있으면 그대로 유지한다. 예) '수미/경진', '가해학생1/2'.
- 앞 줄 대사의 '이어지는 줄'이거나 화자명이 없으면 speaker는 null.
- 절대로 대사 텍스트를 speaker로 반환하지 마라.

입력의 각 줄은 '[TARGET] <id>\\t<본문>' 또는 '[CTX] <id>\\t<본문>' 형식이다.
[CTX] 줄은 앞 문맥일 뿐이니 분류하지 말고, [TARGET] 줄의 id만 정확히 한 번씩 분류해서 반환해라."""


def _format_prompt(target, context):
    lines = [f"[CTX] {gid}\t{text}" for gid, text in context]
    lines += [f"[TARGET] {gid}\t{text}" for gid, text in target]
    return "\n".join(lines)


def _classify_chunk(client, model, target, context):
    resp = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _format_prompt(target, context)},
        ],
        response_format=Classification,
    )
    return resp.choices[0].message.parsed.labels


def classify_lines(api_key, lines, model=CLASSIFY_MODEL, *, _client=None):
    client = _client if _client is not None else OpenAI(api_key=api_key)
    n = len(lines)
    labels = [None] * n

    chunks = []
    start = 0
    while start < n:
        end = min(start + CLASSIFY_CHUNK_LINES, n)
        ctx_start = max(0, start - CONTEXT_LINES)
        context = [(i, lines[i]) for i in range(ctx_start, start)]
        target = [(i, lines[i]) for i in range(start, end)]
        chunks.append((target, context))
        start = end

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_to_ids = {
            ex.submit(_classify_chunk, client, model, target, context):
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


def extract_dialogue_ai(text_list, file_path, api_key, model=CLASSIFY_MODEL, *, _client=None):
    # .xlsx/.xls: 셀이 이미 대사 1줄 — 분류 생략, 지문 괄호 제거만
    if file_path.endswith((".xlsx", ".xls")):
        labels = [LineLabel(id=i, type="dialogue", speaker=None)
                  for i in range(len(text_list))]
        return assemble_dialogue(text_list, labels)

    labels = classify_lines(api_key, text_list, model, _client=_client)
    # 미분류 id는 기존 regex 캐스케이드로 폴백
    for i, lab in enumerate(labels):
        if lab is None:
            hit = extract_speaker_and_dialogue([text_list[i]], file_path)
            labels[i] = LineLabel(
                id=i, type="dialogue" if hit else "other", speaker=None
            )
    return assemble_dialogue(text_list, labels)
```

- [ ] **Step 4: Run the tests to verify GREEN**

Run: `pipenv run python -m pytest tests/test_extract_orchestration.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Full suite green**

Run: `pipenv run python -m pytest -q`
Expected: PASS (19 tests).

- [ ] **Step 6: Commit**

```bash
git add utils/openai_extract.py tests/test_extract_orchestration.py
git commit -m "feat: add chunked AI line classifier with regex fallback and xlsx bypass"
```

---

### Task 4: Pin openai 2.x + bump split model to gpt-5.4

**Files:** Modify `Pipfile`, `utils/openai.py:54`. (No new test — covered by verification.)

- [ ] **Step 1: Pin the SDK floor**

In `Pipfile` `[packages]`, change `openai = "*"` to `openai = ">=2.0"`.

- [ ] **Step 2: Re-lock and sync**

Run: `pipenv lock && pipenv install`
Expected: resolves `openai==2.44.0` (or newer 2.x), lock updated.

- [ ] **Step 3: Bump the 20-char split model**

In `utils/openai.py`, change `model="gpt-4o",` to `model="gpt-5.4",`.

- [ ] **Step 4: Sanity import**

Run: `pipenv run python -c "import openai, utils.openai, utils.openai_extract; print(openai.__version__)"`
Expected: prints a `2.x` version, no import error.

- [ ] **Step 5: Commit**

```bash
git add Pipfile Pipfile.lock utils/openai.py
git commit -m "chore: pin openai>=2.0 and move models to gpt-5.4"
```

---

### Task 5: Integrate into `main.py` + add `convert_cli.py`

**Files:**
- Modify: `main.py` (`FileSelector.convert_file`, imports)
- Create: `convert_cli.py`

**Interfaces:**
- Consumes: `extract_dialogue_ai` (Task 3), `load_api_key` (`utils/json_service.py`), existing `_request_to_ai`, `extract_speaker_and_dialogue`, `data_processing`, `import_file_to_text`, `save_to_word_file`, `request_to_openai`.

- [ ] **Step 1: Add the import in `main.py`**

After the existing `from utils.openai import request_to_openai` line, add:

```python
from utils.openai_extract import extract_dialogue_ai
```

- [ ] **Step 2: Rewrite the body of `convert_file`**

Replace the current sequence (import → extract → data_processing → optional AI) with a branch that loads the key once and keeps the 20-char split separate. In `FileSelector.convert_file`, replace lines from `text_list = import_file_to_text(...)` through the `converted_data = ...` assignment with:

```python
            # import file and convert to text
            text_list = import_file_to_text(self.selected_file_path)

            if self.use_ai.get():
                api_key = load_api_key() or self._input_api_key()   # 키 1회 로드
                dialogue_text = extract_dialogue_ai(
                    text_list, self.selected_file_path, api_key
                )                                                    # AI 분류 추출
                converted_data = self._request_to_ai(dialogue_text)  # 기존 20자 분할
            else:
                speaker_and_dialogue_data = extract_speaker_and_dialogue(
                    text_list, self.selected_file_path
                )
                converted_data = data_processing(
                    "\n".join(speaker_and_dialogue_data)
                )
```

Keep the surrounding `try/except`, `_saved_file_lable` updates, and the `save_to_word_file(...)` call exactly as they are. (`_send_to_ai` still loads the key defensively per chunk — leave it; harmless.)

- [ ] **Step 3: Create `convert_cli.py`**

```python
"""GUI 없이 대본을 변환하는 디버그용 CLI.

  pipenv run python convert_cli.py "경로/파일.docx"          # 기존 regex 추출
  pipenv run python convert_cli.py "경로/파일.docx" --ai      # AI 분류 추출(분할 없음)
  pipenv run python convert_cli.py "경로/파일.docx" --ai --split  # AI 추출 + 20자 분할
"""
import os
import sys

from utils.import_file_to_text import import_file_to_text
from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue
from utils.data_processing import data_processing
from utils.openai_extract import extract_dialogue_ai
from utils.openai import request_to_openai
from utils.json_service import load_api_key
from utils.save_to_word import save_to_word_file

CHUNK_SIZE = 4000


def main():
    argv = sys.argv[1:]
    flags = {a for a in argv if a.startswith("--")}
    positionals = [a for a in argv if not a.startswith("--")]
    if not positionals:
        print('usage: python convert_cli.py "<file>" [--ai] [--split]')
        sys.exit(1)

    path = positionals[0]
    use_ai = "--ai" in flags
    do_split = "--split" in flags

    text_list = import_file_to_text(path)

    if use_ai:
        api_key = load_api_key() or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("API 키 필요: ~/Downloads/settings.json 또는 OPENAI_API_KEY 환경변수")
            sys.exit(1)
        converted = extract_dialogue_ai(text_list, path, api_key)
        if do_split:
            chunks = [converted[i:i + CHUNK_SIZE]
                      for i in range(0, len(converted), CHUNK_SIZE)]
            converted = "\n".join(
                request_to_openai(api_key, data_processing(c)) for c in chunks
            )
    else:
        data = extract_speaker_and_dialogue(text_list, path)
        converted = data_processing("\n".join(data))

    out_name = os.path.basename(path) + "_converted"
    save_to_word_file(converted, out_name)
    print(f"저장: ~/Downloads/{out_name}.docx")
    print("----- 추출 결과 미리보기 -----")
    print("\n".join(converted.split("\n")[:40]))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Smoke-test the AI-OFF path (no network)**

Run: `pipenv run python convert_cli.py "issue/20260630/후아유 방송 01.docx"`
Expected: prints `저장: ~/Downloads/...`, no traceback; preview shows the (unchanged) regex-based extraction.

- [ ] **Step 5: Commit**

```bash
git add main.py convert_cli.py
git commit -m "feat: wire AI extraction into convert_file and add convert_cli"
```

---

### Task 6: Docs + end-to-end verification

**Files:** Modify `README.md`, `CLAUDE.md`.

- [ ] **Step 1: README — add local-run command and AI-ON note**

In `README.md`, under a new `## 로컬 실행 (개발/디버그)` section, add:

````markdown
## 로컬 실행 (개발/디버그)

GUI 없이 파일을 변환해 결과를 확인할 수 있습니다.

```bash
pipenv install
pipenv run python convert_cli.py "경로/대본.docx"            # 규칙 기반 추출
pipenv run python convert_cli.py "경로/대본.docx" --ai        # AI 분류 추출
pipenv run python convert_cli.py "경로/대본.docx" --ai --split  # AI 추출 + 20자 분할
```

AI 옵션은 `~/Downloads/settings.json` 의 `openai_api_key` 또는 `OPENAI_API_KEY` 환경변수를 사용합니다.
````

In the `## 대사 인식 조건` section, add a leading note:

```markdown
> AI 사용 시에는 아래 규칙 대신 모델이 각 줄을 대사/지문/씬헤더로 분류해 추출합니다. 아래 규칙은 AI 미사용(폴백) 시 동작입니다.
```

- [ ] **Step 2: CLAUDE.md — note the AI-ON classification path**

In the "Dialogue detection" section of `CLAUDE.md`, append:

```markdown
When "AI 사용" is ON, `main.py` routes extraction through `utils/openai_extract.py:extract_dialogue_ai` instead: an OpenAI structured-output classifier (`gpt-5.4`) labels each line dialogue/narration/scene/other and returns the bare speaker name; `assemble_dialogue` keeps only dialogue, slices the speaker prefix via `remove_speaker_prefix`, and reuses `remove_inline_directions`. The cascade above is the AI-OFF fallback (also used per-line for any id the model drops). Run headless via `convert_cli.py`.
```

- [ ] **Step 3: Full test suite**

Run: `pipenv run python -m pytest -q`
Expected: PASS (19 tests).

- [ ] **Step 4: AI-OFF regression (no network)**

Run: `pipenv run python convert_cli.py "issue/20260630/후아유 방송 01.docx"`
Compare `~/Downloads/후아유 방송 01.docx_converted.docx` against the committed `issue/20260630/후아유 방송 01.docx_converted.docx` — the retained/dropped lines must match (fallback unchanged).

- [ ] **Step 5: AI-ON verification (requires API key + network)**

Run: `pipenv run python convert_cli.py "issue/20260630/후아유 방송 01.docx" --ai`
In the output `.docx`, verify the three fixes:
- **#3** `생일 축하 합니다! 생일 축하 합니다!` is **present** (was dropped).
- **#1** `서랍에서 통장 두 개 꺼내 보인다. 뿌듯하다.`, `그 위로 경쾌한 생일 축하 노래가 울려 퍼진다.`, `싱그러운 미소로 재잘재잘 수다 떠는 행복한 모습들,` are **absent** (지문 dropped).
- **#2** `수미/경진`, `가해학생1/2` speaker names are **removed** from their dialogue lines.
Cross-check keep/drop against `issue/20260630/후아유 방송 01.docx_converted_answer.docx` (punctuation normalization is out of scope).

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document AI-ON extraction path and local convert CLI"
```

---

## Self-Review

- **Spec coverage:** #1 지문 → classifier `narration` (Task 3 prompt) + drop in `assemble_dialogue` (Task 2). #2 화자명 → `remove_speaker_prefix` slices `/`+digit names (Task 2). #3 `(E)` 누락 → classifier returns bare name, `(E)` survives slice then `remove_inline_directions` strips it (Tasks 2–3). Fallback/xlsx/model/SDK/docs/CLI all have tasks.
- **Placeholder scan:** none — every code step is complete.
- **Type consistency:** `LineLabel(id,type,speaker)` and `Classification(labels)` identical across Tasks 2–3; `extract_dialogue_ai`/`classify_lines` signatures match `convert_file` and `convert_cli` call sites; `remove_inline_directions` name consistent with Task 1.
