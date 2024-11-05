import re

from utils.constants import SPEAKER_DIALOGUE_REGEX_LIST


def extract_speaker_and_dialogue(text_list, file_path) -> list[str]:
    try:
        if file_path.endswith(".xlsx"):
            return text_list

        extracted_dialogues = []
        for text in text_list:
            for regex in SPEAKER_DIALOGUE_REGEX_LIST:
                if re.match(regex, text):
                    extracted_dialogues.append(text)
                    break
        return extracted_dialogues
    except Exception as e:
        print(f"Error in extract_speaker_and_dialogue: {e}")
        raise e
