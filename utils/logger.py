"""날짜별 파일 로깅.

실행파일(또는 개발 시 프로젝트 루트) 옆 `log/` 폴더에 `YYYY-MM-DD.log`로 쌓는다.
그 위치가 쓰기 불가면(macOS App Translocation 등) Application Support로 폴백.
기존 코드의 print() 출력도 함께 파일에 남도록 stdout/stderr를 티(tee)로 감싼다.
"""
import logging
import os
import sys
from datetime import datetime

FALLBACK_DIR = os.path.join(
    os.path.expanduser("~"), "Library", "Application Support", "ScriptShaper"
)

_original_stdout = None
_original_stderr = None
_file_handler = None


def _base_dir():
    if getattr(sys, "frozen", False):  # PyInstaller 바이너리
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 프로젝트 루트


class _Tee:
    """print/에러 출력을 원래 스트림과 로그 파일에 동시에 쓴다."""

    def __init__(self, stream, logfile_path):
        self._stream = stream
        self._path = logfile_path

    def write(self, data):
        try:
            self._stream.write(data)
        except Exception:
            pass  # 콘솔 없는 배포 실행(GUI)에서도 로그는 남긴다
        if data.strip():
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(data if data.endswith("\n") else data + "\n")

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass


def setup_logging(base_dir=None):
    """로깅 초기화. 생성된 로그 파일 경로를 반환."""
    global _original_stdout, _original_stderr, _file_handler

    base = base_dir or _base_dir()
    log_dir = os.path.join(base, "log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        probe = os.path.join(log_dir, ".write_probe")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
    except OSError:
        # 실행파일 위치가 쓰기 불가 → Application Support 폴백
        log_dir = os.path.join(FALLBACK_DIR, "log")
        os.makedirs(log_dir, exist_ok=True)

    logfile = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d") + ".log")

    _file_handler = logging.FileHandler(logfile, encoding="utf-8")
    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(_file_handler)

    # 기존 print() 출력도 로그로
    _original_stdout, _original_stderr = sys.stdout, sys.stderr
    sys.stdout = _Tee(_original_stdout, logfile)
    sys.stderr = _Tee(_original_stderr, logfile)

    # 로그 파일 생성 보장 + 시작 기록
    logging.info("==== ScriptShaper 시작 (log: %s) ====", logfile)
    return logfile


def teardown_logging():
    """테스트용: 핸들러/티 원복."""
    global _original_stdout, _original_stderr, _file_handler
    if _file_handler is not None:
        logging.getLogger().removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None
    if _original_stdout is not None:
        sys.stdout = _original_stdout
        _original_stdout = None
    if _original_stderr is not None:
        sys.stderr = _original_stderr
        _original_stderr = None
