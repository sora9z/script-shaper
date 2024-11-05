from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import simpledialog

from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue
from utils.data_processing import data_processing
from utils.import_file_to_text import import_file_to_text
from utils.json_service import load_api_key, save_api_key
from utils.openai import request_to_openai
from utils.save_to_word import save_to_word_file

CHUNK_SIZE = 4000


class FileSelector:
    def __init__(self, root):
        self.root = root
        self.selected_file = None
        self.use_ai = tk.BooleanVar(value=True)

        # 파일 경로를 보여줄 레이블
        self.file_lable = tk.Label(root, text="선택된 파일 없음", wraplength=500)
        self.file_lable.pack(pady=20)

        # 저장된 파일 경로를 보여줄 레이블
        self._saved_file_lable = tk.Label(
            root, text="저장된 파일 경로:", wraplength=500
        )
        self._saved_file_lable.pack(pady=20)

        # 파일 선택 버틍
        self.select_button = tk.Button(
            root,
            text="파일 선택",
            command=self.select_file,
            width=15,
            height=3,
        )
        self.select_button.pack(pady=5)

        # 임포트 버틍 (처음엔 비활성화)
        self.import_button = tk.Button(
            root,
            text="파일 임포트",
            command=self.convert_file,
            width=15,
            height=3,
            state="disabled",  # 처음에는 비활성화
        )
        self.import_button.pack(pady=5)

        # ai 사용 여부 체크박스
        self.ai_checkbox = tk.Checkbutton(
            root,
            text="AI 사용",
            variable=self.use_ai,
            onvalue=True,
            offvalue=False,
        )
        self.ai_checkbox.pack(pady=5)

        # 로그를 보여줄 텍스트 위젯
        # self.log_text = tk.Text(root, height=10, width=70)
        # self.log_text.pack(pady=10))

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="파일 선택",
            filetypes=[
                ("Word documents_docx", "*.docx"),
                ("Word documents_doc", "*.doc"),
                ("Excel files", "*.xlsx"),
                ("CSV files", "*.csv"),
                ("PDF files", "*.pdf"),
                ("Text files", "*.txt"),
                ("HWP files", "*.hwp"),
            ],
        )
        if file_path:
            self.selected_file_path = file_path
            self.file_lable.config(text=f"선택된 파일: {file_path}")
            self.import_button.config(
                state="normal"
            )  # 파일이 선택되면 임포트 버튼 활성화

    def convert_file(self):
        try:
            self._saved_file_lable.config(text=f"저장된 파일 경로: ")
            # import file and convert to text
            text_list = import_file_to_text(self.selected_file_path)
            # extract speaker and dialogue
            speaker_and_dialogue_data = extract_speaker_and_dialogue(
                text_list, self.selected_file_path
            )
            # text data processing
            processed_data = data_processing("\n".join(speaker_and_dialogue_data))
            # request to openai by parallel processing
            if self.use_ai.get():
                converted_data = self._request_to_ai(processed_data)
            else:
                converted_data = processed_data

            # save to word file
            file_name = os.path.basename(self.selected_file_path)
            save_to_word_file(converted_data, file_name + "_converted")
            self._saved_file_lable.config(
                text=f"저장된 파일 경로: {file_name + '_converted.docx'}"
            )

        except Exception as e:
            print(f"Error in convert_file: {e}")
            messagebox.showerror("Error", str(e))

    def _request_to_ai(self, processed_data: str):
        print("AI 요청 중...")
        # 긴 텍스트를 일정 크기(chunk_size)로 나누는 작업
        text_chunks = [
            processed_data[i : i + CHUNK_SIZE]
            for i in range(0, len(processed_data), CHUNK_SIZE)
        ]

        # 결과를 저장할 리스트
        converted_data_chunks = [None] * len(text_chunks)
        # 쓰레드 풀을 사용한 병렬 처리
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_index = {
                executor.submit(
                    self._process_chunk,
                    chunk,
                    index,
                    len(processed_data),
                    text_chunks,
                ): index
                for index, chunk in enumerate(text_chunks)
            }

            # 청크들을 순서대로 합침
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                # 원래 인덱스 위치에 저장
                converted_data_chunks[index] = future.result()
            except Exception as e:
                print(f"청크 {index} 처리 중 오류 발생: {e}")
                messagebox.showerror("Error", f"청크 {index} 처리 실패: {str(e)}")
                # 청크들을 순서대로 합침
        return "\n".join(chunk for chunk in converted_data_chunks if chunk is not None)

    def _process_chunk(self, chunk, index, total_length, text_chunks):
        """단일 청크를 처리하는 메서드"""
        processed_chunk = data_processing(chunk)
        if self.use_ai:
            print(
                f"청크 처리 중 {index + 1}/{len(text_chunks)} (전체 길이: {total_length})"
            )
            processed_chunk = self._send_to_ai(processed_chunk)
        return processed_chunk

    def _send_to_ai(self, converted_data):
        api_key = load_api_key()
        if not api_key:
            messagebox.showinfo("API 키 필요", "OpenAI API 키가 필요합니다.")
            api_key = self._input_api_key()

        result = request_to_openai(api_key, converted_data)
        return result

    def _input_api_key(self):
        api_key = simpledialog.askstring("API 키 입력", "OpenAI API 키를 입력하세요:")
        if api_key:
            save_api_key(api_key)
            return api_key
        else:
            raise ValueError("API 키가 입력되지 않았습니다.")


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Script Shaper")
    root.geometry("800x400")

    app = FileSelector(root)
    root.mainloop()
