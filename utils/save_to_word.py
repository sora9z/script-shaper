import os
from docx import Document


def save_to_word_file(converted_data, file_name):
    # MacBook의 기본 다운로드 폴더 경로 가져오기
    download_path = os.path.join(os.path.expanduser("~"), "Downloads")
    # 최종 출력 경로
    output_path = os.path.join(download_path, file_name + ".docx")
    print(f"Saving to: {output_path}")
    try:
        doc = Document()
        for paragraph in converted_data.split("\n"):
            if paragraph.strip():
                doc.add_paragraph(paragraph)
        doc.save(output_path)
    except Exception as e:
        print(f"Error in save_to_word_file: {e}")
        raise e
