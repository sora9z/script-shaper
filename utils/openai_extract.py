from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel

from utils.data_processing import remove_inline_directions
from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue

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
