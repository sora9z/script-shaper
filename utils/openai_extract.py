import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel

from utils.constants import SPEAKER_DIALOGUE_REGEX_LIST
from utils.data_processing import remove_inline_directions, data_processing
from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue

MAX_SPEAKER_LEN = 12
_BOUNDARY = set(" \t([{:")          # 화자명 뒤에 올 수 있는 구분자(콜론 포함)
_SEP_STRIP = " \t:"                 # 잘라낼 구분자(괄호는 지문이라 보존)


class LineLabel(BaseModel):
    id: int
    type: Literal["dialogue", "narration", "scene", "other"]
    speaker: Optional[str] = None


class Classification(BaseModel):
    labels: list[LineLabel]


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
    return rest.lstrip(_SEP_STRIP)        # 콜론/공백 구분자 제거(괄호 지문은 보존)


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


# 대사에서 제거할 기호(정답 스타일): 물음표/느낌표/말줄임/물결/쉼표/세미콜론/따옴표/마침표
_PUNCT_STRIP_RE = re.compile(r"[?!…~,;·\"'“”‘’.]+")


def normalize_dialogue(text: str) -> str:
    """추출된 대사를 자막용으로 정규화한다 (결정적 규칙, AI 미사용).

    - 기호 제거: ? ! … ~ , ; 따옴표, 내부 마침표/말줄임
    - 공백 정리 후 각 줄 끝에 마침표 하나 (하류 자막 툴이 '.' 기준으로 문장 구분)
    - 기호만 남은/빈 줄은 버림
    """
    kept = []
    for ln in text.split("\n"):
        core = _PUNCT_STRIP_RE.sub(" ", ln)
        core = re.sub(r"\s{2,}", " ", core).strip()
        if core:
            kept.append(core + ".")
    return "\n".join(kept)


CLASSIFY_MODEL = "gpt-5.4"
CLASSIFY_CHUNK_LINES = 50
CONTEXT_LINES = 5
MAX_WORKERS = 5

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
            for j in range(end + 1, min(end + extend + 1, n)):
                if _is_boundary(lines[j]):
                    end = j
                    break
        chunks.append((start, end))
        start = end
    return chunks


_PATTERN_SYSTEM_PROMPT = """너는 대본 문서의 '표기 형식'을 분석하는 분석기다.
아래 대본 샘플을 보고, 이 문서에서 '화자줄'(등장인물 화자명으로 시작하는 대사 줄)의 형식 패턴을 찾아라.
목표는 단 하나, 화자줄을 판정하는 regex다. 지문(내레이션)은 regex로 구분할 수 없으니 시도하지 마라.

[화자줄 형식은 문서마다 다르다 — 대표 유형]
- 콜론형: '민수: 안녕하세요'
- 공백/탭형: '은비    학교요?' (이름 뒤 공백 여러 칸 또는 탭)
- 붙음형: '은수(N)시작부터 정해져 있었다' (이름과 대사 사이 구분자가 전혀 없음 — 실제로 흔함)
어느 유형인지, 혹은 혼합인지 샘플에서 확인하고 그 형식만 정확히 표현해라.

[화자명에 올 수 있는 것들]
- 한글/영문 이름, 숫자 접미(기자1, 가해학생1/2), 다인 화자(수미/경진, 동현,준현), 언더스코어(어부_)
- 이름 뒤 기술 표기: (E), (N), (F), (O.L) 등 — 붙거나 한 칸 띄고 옴. 이런 표기는 화자줄의 일부다.

[반환 규칙]
- speaker_line_regex: 화자줄만 매치하는 Python regex. 반드시 '^'로 시작(줄 앞 앵커), 200자 이내.
  * 씬 헤더를 매치하면 안 된다. 주의: 씬 헤더가 인물 이름으로 시작하는 경우가 있다
    (예: '은수 집, 주방 (D)' — 이것은 화자줄이 아니라 장소 표기다). regex가 이런 줄을 물지 않는지 확인해라.
  * 지문 줄('...보인다.', '...간다.')을 매치하면 안 된다.
- **이 문서에 화자줄이 아예 없으면** (자막 리스트, SRT 등 — 순번/타임코드/컷번호만 있고 화자 표기가 없는 문서)
  speaker_line_regex를 빈 문자열("")로 반환해라. 순번(예: '1179'), 타임코드(예: '00:12:03,450 --> ...'),
  컷번호(예: '755B')는 화자줄이 아니다. 억지로 regex를 만들지 마라.
- scene_header_regex: 씬 헤더 형식이 명확할 때만('#1.', '12. 장소 (D)' 등, '^' 앵커). 불확실하면 null.
- pattern_description: 이 문서에서 화자줄을 알아보는 방법을 2~3문장의 한국어로.
- speaker_examples: 샘플에 실제로 존재하는 화자줄 2~5개를 글자 그대로 복사. 페이지 머리글(파일명),
  순번, 타임코드, 컷번호, 씬 헤더는 예시로 넣지 마라. 화자줄이 없으면 빈 배열.

[검산] 화자줄은 보통 전체 줄의 5~60%다. 네 regex가 거의 모든 줄이나 거의 0줄에 매치된다면 잘못된 것이다."""


def _boundary_union(speaker_re):
    """청킹 경계 판정용: 학습된 문서별 regex + baseline 화자 패턴(콜론형·3+공백형)의 결합.

    경계 판정은 오탐/미탐 비용이 낮아 넓게 잡는다. 단, 매치율 검증(validate_pattern)은
    학습 regex 단독으로 수행 — baseline(특히 과잉 콜론형)을 섞으면 학습 실패가 가려진다.
    """
    parts = [speaker_re.pattern] + list(SPEAKER_DIALOGUE_REGEX_LIST)
    return re.compile("|".join(f"(?:{p})" for p in parts))


def analyze_pattern(api_key, lines, model=CLASSIFY_MODEL, *, _client=None):
    """문서 1회 패턴 분석. 어떤 실패든 None(→ 현행 방식으로 폴백)."""
    try:
        client = _client if _client is not None else OpenAI(api_key=api_key)
        sample = "\n".join(sample_windows(lines))
        resp = client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": _PATTERN_SYSTEM_PROMPT},
                {"role": "user", "content": sample},
            ],
            response_format=ScriptPattern,
        )
        parsed = resp.choices[0].message.parsed
        if not isinstance(parsed, ScriptPattern):
            logging.warning("패턴 분석: 응답 형식 불일치 → 고정 청킹으로 진행")
            return None
        logging.info("패턴 분석 완료: regex=%r", parsed.speaker_line_regex)
        return parsed
    except Exception as e:
        logging.warning("패턴 분석 실패(고정 청킹으로 진행): %s", e)
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


def classify_lines(api_key, lines, model=CLASSIFY_MODEL, *, _client=None,
                   pattern=None, speaker_re=None, scene_re=None):
    client = _client if _client is not None else OpenAI(api_key=api_key)
    n = len(lines)
    labels = [None] * n

    # 패턴이 검증된 경우: 화자 경계 정렬 청킹 + 프롬프트 주입. 아니면 현행 고정 청킹.
    system_prompt = _SYSTEM_PROMPT
    if pattern is not None and speaker_re is not None:
        system_prompt = _SYSTEM_PROMPT + _pattern_prompt_block(pattern)
        # 경계 판정은 학습 regex + baseline 화자 패턴의 union으로 (넓게, 안전)
        ranges = chunk_by_speaker_boundaries(lines, _boundary_union(speaker_re), scene_re)
        logging.info("분류 시작: %d줄 → %d청크 (패턴 경계 정렬)", n, len(ranges))
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
                logging.warning(
                    "청크 분류 실패(줄 %d~%d): %s",
                    min(valid_ids), max(valid_ids), e,
                )
    return labels


def extract_dialogue_ai(text_list, file_path, api_key, model=CLASSIFY_MODEL, *, _client=None):
    # .xlsx/.xls: 셀이 이미 대사 1줄 — 분류 생략. OFF 경로와 동일하게
    # data_processing으로 화자명·지문을 제거(콜론/3+공백 화자명 포함).
    if file_path.endswith((".xlsx", ".xls")):
        return normalize_dialogue(data_processing("\n".join(text_list)))

    # 문서 1회 패턴 분석 → 검증 실패 시 None(현행 경로)
    pattern = analyze_pattern(api_key, text_list, model, _client=_client)
    speaker_re = scene_re = None
    if pattern is not None:
        speaker_re, scene_re = validate_pattern(pattern, text_list)
        if speaker_re is None:
            logging.warning("패턴 검증 탈락(빈/과잉/컴파일 불가 regex) → 고정 청킹으로 진행")
            pattern = None

    labels = classify_lines(api_key, text_list, model, _client=_client,
                            pattern=pattern, speaker_re=speaker_re, scene_re=scene_re)
    lines = list(text_list)
    # 미분류 id는 기존 regex 캐스케이드로 폴백
    fallback_count = 0
    for i, lab in enumerate(labels):
        if lab is None:
            # 주의: 폴백은 기존 규칙 경로라, ~다로 끝나는 지문이 다시 대사로 샐 수 있음(모델 미분류 시 한정)
            fallback_count += 1
            hit = extract_speaker_and_dialogue([text_list[i]], file_path)
            if hit:
                # 폴백: 기존 규칙 경로와 동일하게 화자명·지문 제거
                lines[i] = data_processing(text_list[i])
                labels[i] = LineLabel(id=i, type="dialogue", speaker=None)
            else:
                labels[i] = LineLabel(id=i, type="other", speaker=None)
    if fallback_count:
        # 이 수치가 크면 결과 품질 저하(지문 잔존 등)의 원인일 수 있음
        logging.warning("모델 미분류 %d/%d줄 → regex 폴백 처리됨", fallback_count, len(text_list))
    # 최종 정규화: 기호 제거 + 줄끝 마침표 (정답 자막 스타일, 결정적 규칙)
    return normalize_dialogue(assemble_dialogue(lines, labels))
