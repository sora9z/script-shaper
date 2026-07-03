import logging
import os

from docx import Document


def save_to_word_file(converted_data, file_name, output_dir=None):
    # 저장 폴더: 지정 없으면 기본 다운로드 폴더 (GUI 기본 동작)
    if output_dir is None:
        output_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    # 최종 출력 경로
    output_path = os.path.join(output_dir, file_name + ".docx")
    doc = Document()
    for paragraph in converted_data.split("\n"):
        if paragraph.strip():
            doc.add_paragraph(paragraph)
    doc.save(output_path)
    logging.info("결과 저장 완료: %s", output_path)
