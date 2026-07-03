import logging

from utils.file_reader_list import read_file

"""
def import_file_to_text.__doc__():
import_file_to_text 함수는 주어진 파일 경로(selected_file_path)의 파일을 읽어서 텍스트 형태로 반환합니다.
내부적으로 utils.file_reader_list 모듈의 read_file 함수를 사용하여 다양한 파일 형식(docx, pdf, txt 등)을 처리할 수 있습니다.
파일 경로가 유효하지 않거나 오류가 발생할 경우 예외가 발생하며, 올바르게 읽은 경우 파일의 텍스트 내용을 리스트 형태로 반환합니다.
"""


def import_file_to_text(selected_file_path):
    if not selected_file_path:
        logging.warning("import_file_to_text: 선택된 파일 없음")
        return None
    text_data = read_file(selected_file_path)
    logging.info(
        "파일 임포트: %s (%d줄)",
        selected_file_path,
        len(text_data) if text_data else 0,
    )
    return text_data
