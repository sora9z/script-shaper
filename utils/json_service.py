import json
import os


# 고정된 위치 설정 (예: 사용자의 다운로드 디렉토리)
download_path = os.path.join(os.path.expanduser("~"), "Downloads")
SETTINGS_PATH = os.path.join(download_path, "settings.json")


def save_api_key(api_key):
    """API 키를 settings.json 파일에 저장"""
    settings = {"openai_api_key": api_key}
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f)
    print(f"API 키가 {SETTINGS_PATH}에 저장되었습니다.")


def load_api_key():
    """settings.json 파일에서 API 키를 로드"""
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r") as f:
            settings = json.load(f)
        return settings.get("openai_api_key")
    return None


def get_api_key():
    """API 키를 가져오거나 사용자로부터 입력받아 저장"""
    api_key = load_api_key()
    if not api_key:
        api_key = input("OpenAI API 키를 입력하세요: ").strip()
        if api_key:
            save_api_key(api_key)
        else:
            raise ValueError("API 키가 입력되지 않았습니다.")
    return api_key
