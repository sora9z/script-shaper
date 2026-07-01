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
