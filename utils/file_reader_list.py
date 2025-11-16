"""
파일 읽기 유틸리티
Word, Excel, CSV, PDF, HWP 파일을 읽어서 텍스트로 변환
"""

from docx import Document
from pdfminer.high_level import extract_text
import pandas as pd


"""
read_file 함수는 다양한 파일 형식(Word의 .docx, Excel의 .xlsx/.xls, 지원 중단된 .doc, PDF, CSV, HWP 등)의 파일을 읽어서 텍스트 데이터를 리스트 형태로 반환합니다.
입력 경로(file_path)의 확장자를 기반으로 각각의 파일 타입별로 적절한 패키지와 파싱 방법을 사용하여 파일 내용을 읽어옵니다.
주로 각 텍스트의 줄(또는 셀, 단락) 단위로 분할하여 반환하며, 파일이 지원하지 않는 형식(.doc 등)일 경우 예외(Exception)를 발생시킵니다.
PDF, HWP, CSV 등 다른 포맷의 처리는 추가 구현이 필요할 수 있습니다.
추출되는 텍스트 예시
- 화자명   대사
- 화자명 : 대사
"""


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
