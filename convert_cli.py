"""GUI 없이 대본을 변환하는 디버그용 CLI.

  pipenv run python convert_cli.py "경로/파일.docx"          # 기존 regex 추출
  pipenv run python convert_cli.py "경로/파일.docx" --ai      # AI 분류 추출(분할 없음)
  pipenv run python convert_cli.py "경로/파일.docx" --ai --split  # AI 추출 + 20자 분할
  pipenv run python convert_cli.py "경로/파일.docx" --ai --out issue/20260630  # 저장 폴더 지정
"""
import logging
import os
import sys

logging.basicConfig(format="%(levelname)s %(message)s", level=logging.INFO)  # CLI는 콘솔로

from utils.import_file_to_text import import_file_to_text
from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue
from utils.data_processing import data_processing
from utils.openai_extract import extract_dialogue_ai
from utils.openai import request_to_openai
from utils.json_service import load_api_key
from utils.save_to_word import save_to_word_file

CHUNK_SIZE = 4000


def main():
    argv = sys.argv[1:]
    # --out <dir> 는 값을 갖는 옵션이라 먼저 분리
    output_dir = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            print("--out 뒤에 저장 폴더 경로가 필요합니다")
            sys.exit(1)
        output_dir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    flags = {a for a in argv if a.startswith("--")}
    positionals = [a for a in argv if not a.startswith("--")]
    if not positionals:
        print('usage: python convert_cli.py "<file>" [--ai] [--split] [--out <dir>]')
        sys.exit(1)

    path = positionals[0]
    use_ai = "--ai" in flags
    do_split = "--split" in flags

    text_list = import_file_to_text(path)

    if use_ai:
        api_key = load_api_key() or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("API 키 필요: ~/Downloads/settings.json 또는 OPENAI_API_KEY 환경변수")
            sys.exit(1)
        converted = extract_dialogue_ai(text_list, path, api_key)
        if do_split:
            chunks = [converted[i:i + CHUNK_SIZE]
                      for i in range(0, len(converted), CHUNK_SIZE)]
            converted = "\n".join(
                request_to_openai(api_key, data_processing(c)) for c in chunks
            )
    else:
        data = extract_speaker_and_dialogue(text_list, path)
        converted = data_processing("\n".join(data))

    out_name = os.path.basename(path) + "_converted"
    save_to_word_file(converted, out_name, output_dir=output_dir)
    shown_dir = output_dir if output_dir else "~/Downloads"
    print(f"저장: {shown_dir}/{out_name}.docx")
    print("----- 추출 결과 미리보기 -----")
    print("\n".join(converted.split("\n")[:40]))


if __name__ == "__main__":
    main()
