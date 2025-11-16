import re

from utils.constants import SPEAKER_DIALOGUE_REGEX_LIST


"""
화자명과 대사
def extract_speaker_and_dialogue.__doc__():
extract_speaker_and_dialogue 함수는 입력으로 받은 텍스트 리스트(text_list)에서 정규표현식(SPEAKER_DIALOGUE_REGEX_LIST)을 활용하여,
대사 유형("화자명: 대사", "화자명    대사" 등)에 해당하는 텍스트만 필터링하여 추출합니다.
파일 경로(file_path)의 확장자명에 따라, 예를 들어 Excel 파일(.xlsx)일 경우에는 별도의 전처리 없이 원본 리스트를 그대로 반환하고,
그 외의 경우에는 각 텍스트에 대해 정규표현식을 순차적으로 적용하여 조건에 맞는 대사 라인만 모아 새로운 리스트로 반환합니다.
반환값은 대사가 식별된 텍스트의 리스트입니다.
"""


def extract_speaker_and_dialogue(text_list, file_path) -> list[str]:
    try:
        if file_path.endswith(".xlsx"):
            return text_list

        DIALOGUE_END_PUNCTUATION = [
            "!", "?", "…", "...", "~", ",", ";", '"'
        ]

        KOREAN_DIALOGUE_ENDINGS = [
            "요", "죠", "네요", "군요", "구나", "구나요", "합니다", "이에요", "예요", "옵니다",
            "드립니다", "습니까", "다", "라", "냐", "니", "네", "해", "했어", "할게", "할까",
            "지", "자", "구먼", "구먼요", "잖아", "잖아요", "거든요", "말이야", "말입니다"
        ]

        extracted_dialogues = []
        for text in text_list:
            is_dialogue = False

            # 기존 regex 패턴으로 체크
            for regex in SPEAKER_DIALOGUE_REGEX_LIST:
                if re.match(regex, text):
                    extracted_dialogues.append(text)
                    is_dialogue = True
                    break

            # 이미 대사로 인식되었으면 스킵
            if is_dialogue:
                continue

            # 대사 종료 문장부호로 끝나는지 체크
            stripped_text = text.strip()
            for punctuation in DIALOGUE_END_PUNCTUATION:
                if stripped_text.endswith(punctuation):
                    extracted_dialogues.append(text)
                    is_dialogue = True
                    break

            # 이미 대사로 인식되었으면 스킵
            if is_dialogue:
                continue

            # 한국어 대사체 어미로 끝나는지 체크
            for ending in KOREAN_DIALOGUE_ENDINGS:
                if stripped_text.endswith(ending):
                    extracted_dialogues.append(text)
                    break

        return extracted_dialogues
    except Exception as e:
        print(f"Error in extract_speaker_and_dialogue: {e}")
        raise e
