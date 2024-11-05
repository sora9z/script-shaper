"""
파일 읽기 유틸리티
Word, Excel, CSV, PDF, HWP 파일을 읽어서 텍스트로 변환
"""

from docx import Document
from pdfminer.high_level import extract_text
import pandas as pd


def read_file(file_path: str):
    print("read_file start", file_path)
    try:
        if file_path.endswith(".docx"):
            extract_file = Document(file_path)
            return [
                para.text.strip().replace(
                    "\t", "    "
                )  # 일부러공백을 많이 줘서 화자명을 구분하기 위함
                for para in extract_file.paragraphs
                if len(para.text.strip()) > 0
            ]

        elif file_path.endswith(".doc"):
            raise Exception(
                "doc 파일은 지원하지 않습니다. docx 파일로 변환 후 사용해주세요."
            )

        elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
            df = pd.read_excel(file_path)
            df.dropna(how="all", inplace=True)  # 모든 열이 비어있는 행 제거

            # 줄바꿈 제거
            remove_enter = df.astype(str).apply(lambda x: " ".join(x), axis=1)
            data_list = remove_enter.tolist()
            return [item.strip() for data in data_list for item in data.split("\n")]

    except Exception as e:
        print(e)
        raise e
