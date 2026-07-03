import json

from utils import json_service


def _patch_paths(monkeypatch, tmp_path):
    new = tmp_path / "AppSupport" / "settings.json"
    legacy = tmp_path / "Downloads" / "settings.json"
    monkeypatch.setattr(json_service, "SETTINGS_PATH", str(new))
    monkeypatch.setattr(json_service, "LEGACY_SETTINGS_PATH", str(legacy))
    return new, legacy


def test_save_then_load_roundtrip(monkeypatch, tmp_path):
    new, _ = _patch_paths(monkeypatch, tmp_path)
    json_service.save_api_key("sk-test-123")           # 디렉터리 자동 생성 포함
    assert json_service.load_api_key() == "sk-test-123"
    assert json.load(open(new))["openai_api_key"] == "sk-test-123"


def test_save_preserves_other_settings(monkeypatch, tmp_path):
    new, _ = _patch_paths(monkeypatch, tmp_path)
    new.parent.mkdir(parents=True)
    new.write_text(json.dumps({"openai_api_key": "old", "theme": "dark"}))
    json_service.save_api_key("sk-new")
    saved = json.load(open(new))
    assert saved["openai_api_key"] == "sk-new"
    assert saved["theme"] == "dark"                    # 다른 설정 보존


def test_load_migrates_legacy_downloads_key(monkeypatch, tmp_path):
    new, legacy = _patch_paths(monkeypatch, tmp_path)
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"openai_api_key": "sk-legacy"}))
    assert json_service.load_api_key() == "sk-legacy"  # 레거시에서 읽고
    assert json.load(open(new))["openai_api_key"] == "sk-legacy"  # 새 위치로 이관


def test_load_returns_none_when_nowhere(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    assert json_service.load_api_key() is None


def test_generic_setting_roundtrip(monkeypatch, tmp_path):
    new, _ = _patch_paths(monkeypatch, tmp_path)
    json_service.save_setting("output_dir", "/tmp/결과폴더")
    assert json_service.load_setting("output_dir") == "/tmp/결과폴더"
    # 기존 api 키와 공존
    json_service.save_api_key("sk-x")
    assert json_service.load_setting("output_dir") == "/tmp/결과폴더"
    assert json_service.load_api_key() == "sk-x"


def test_load_setting_none_when_missing(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    assert json_service.load_setting("output_dir") is None
