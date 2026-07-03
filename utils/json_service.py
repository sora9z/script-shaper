import json
import logging
import os


# 설정 저장 위치: macOS 표준 앱 설정 디렉터리
SETTINGS_DIR = os.path.join(
    os.path.expanduser("~"), "Library", "Application Support", "ScriptShaper"
)
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

# 구버전 위치(~/Downloads) — 발견 시 새 위치로 자동 이관
LEGACY_SETTINGS_PATH = os.path.join(
    os.path.expanduser("~"), "Downloads", "settings.json"
)


def _read_settings(path):
    """settings dict 반환. 없거나 깨졌으면 None."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError):
        return None


def save_setting(key, value):
    """설정 값 하나를 settings.json에 저장 (다른 키는 보존)"""
    settings = _read_settings(SETTINGS_PATH) or {}
    settings[key] = value
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f)


def load_setting(key):
    """settings.json에서 설정 값 하나를 로드. 없으면 None."""
    settings = _read_settings(SETTINGS_PATH)
    return settings.get(key) if settings else None


def save_api_key(api_key):
    """API 키를 settings.json에 저장 (다른 설정 키는 보존)"""
    save_setting("openai_api_key", api_key)
    logging.info("API 키 저장됨: %s", SETTINGS_PATH)  # 키 값은 로그에 남기지 않음


def load_api_key():
    """settings.json에서 API 키 로드. 구버전(~/Downloads) 발견 시 새 위치로 이관."""
    settings = _read_settings(SETTINGS_PATH)
    if settings and settings.get("openai_api_key"):
        return settings["openai_api_key"]

    # 구버전 위치 폴백 + 이관
    legacy = _read_settings(LEGACY_SETTINGS_PATH)
    if legacy and legacy.get("openai_api_key"):
        save_api_key(legacy["openai_api_key"])
        return legacy["openai_api_key"]
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
