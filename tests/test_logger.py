import logging
import os
from datetime import datetime

import pytest

from utils import logger as logger_mod


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    # 각 테스트 후 핸들러/티 원복
    logger_mod.teardown_logging()


def test_setup_creates_dated_logfile_under_base(tmp_path):
    logfile = logger_mod.setup_logging(base_dir=str(tmp_path))
    today = datetime.now().strftime("%Y-%m-%d")
    assert logfile == os.path.join(str(tmp_path), "log", f"{today}.log")
    assert os.path.exists(logfile)


def test_logging_and_print_are_captured(tmp_path):
    logfile = logger_mod.setup_logging(base_dir=str(tmp_path))
    logging.getLogger().info("로그 메시지 확인")
    print("프린트 메시지 확인")
    content = open(logfile, encoding="utf-8").read()
    assert "로그 메시지 확인" in content
    assert "프린트 메시지 확인" in content


def test_exception_logged_with_traceback(tmp_path):
    logfile = logger_mod.setup_logging(base_dir=str(tmp_path))
    try:
        raise ValueError("의도된 에러")
    except ValueError:
        logging.exception("변환 실패")
    content = open(logfile, encoding="utf-8").read()
    assert "변환 실패" in content
    assert "ValueError: 의도된 에러" in content
    assert "Traceback" in content


def test_fallback_when_base_not_writable(tmp_path, monkeypatch):
    ro = tmp_path / "readonly"
    ro.mkdir()
    ro.chmod(0o555)  # 쓰기 불가
    fallback = tmp_path / "appsupport"
    monkeypatch.setattr(logger_mod, "FALLBACK_DIR", str(fallback))
    logfile = logger_mod.setup_logging(base_dir=str(ro))
    assert str(fallback) in logfile
    assert os.path.exists(logfile)
