"""
    텍스트 데이터 전처리
    1. 화자명 제거
    2. 지시어 제거 (괄호, 중괄호, 대괄호)
    3. 문장 마지막에 . 추가 -> 운하 프로그램에서 .을 기준으로 문장을 구분한다.
    """

import re
from utils.constants import SPEAKER_DIALOGUE_REGEX_LIST


def remove_inline_directions(text_data: str) -> str:
    """괄호/대괄호/중괄호 안의 지시어(지문)를 제거한다.

    - 균형 잡힌 (), [], {} 그룹 제거
    - 각 라인 끝에 닫히지 않은 괄호는 줄 끝까지 제거
    화자명은 건드리지 않는다(호출부에서 별도 처리).
    """
    # 지시어 제거 (괄호, 중괄호, 대괄호 제거)
    text_data = re.sub(
        r"\(\s*[^()]*\s*\)|\[\s*[^\[\]]*\s*\]|\{\s*[^{}]*\s*\}",
        "",
        text_data,
    )

    # 각 라인 끝에 있는 닫히지 않은 괄호들만 제거
    text_data = re.sub(r"\([^)\n]*(?=\n|$)", "", text_data)
    text_data = re.sub(r"\[[^\]\n]*(?=\n|$)", "", text_data)
    text_data = re.sub(r"\{[^}\n]*(?=\n|$)", "", text_data)
    return text_data


def data_processing(text_data: str) -> list[str]:
    try:
        # 화자명 제거 SPEAKER_DIALOGUE_REGEX_LIST에 해당하는 문장 제거
        for regex in SPEAKER_DIALOGUE_REGEX_LIST:
            text_data = re.sub(regex, "", text_data, flags=re.MULTILINE)

        # 지시어 제거 (괄호, 중괄호, 대괄호 제거)
        text_data = remove_inline_directions(text_data)

        # 문장 마지막에 . 추가
        # text_data = re.sub(
        #     r"([a-zA-Z0-9가-힣])(?![.,])\s*$", r"\1.", text_data, flags=re.MULTILINE
        # )
    except Exception as e:
        print(f"Error in data_processing: {e}")
        raise e
    return text_data
