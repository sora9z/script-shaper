from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import os
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import simpledialog

from utils.extract_speaker_and_dialogue import extract_speaker_and_dialogue
from utils.data_processing import data_processing
from utils.import_file_to_text import import_file_to_text
from utils.json_service import load_api_key, save_api_key, load_setting, save_setting
from utils.logger import setup_logging
from utils.openai import request_to_openai
from utils.openai_extract import extract_dialogue_ai
from utils.save_to_word import save_to_word_file

CHUNK_SIZE = 4000


class FileSelector:
    def __init__(self, root):
        self.root = root
        self.selected_file = None
        self.use_ai = tk.BooleanVar(value=True)  # AI 사용이 기본값

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

        # 임포트 버튼 (처음엔 비활성화)
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

        # 설정 버튼 (OpenAI API 키 등록/변경)
        self.settings_button = tk.Button(
            root,
            text="설정",
            command=self.open_settings,
            width=15,
            height=2,
        )
        self.settings_button.pack(pady=5)

        # 로그를 보여줄 텍스트 위젯
        self.log_text = tk.Text(root, height=10, width=70)
        self.log_text.pack(pady=10)

    def open_settings(self):
        """설정 창: OpenAI API 키 입력 → settings.json에 저장"""
        win = tk.Toplevel(self.root)
        win.title("설정")
        win.geometry("460x260")
        win.transient(self.root)
        win.grab_set()  # 모달

        current = load_api_key()
        status = f"현재 키: {current[:7]}···{current[-4:]}" if current else "등록된 키 없음"
        tk.Label(win, text=f"OpenAI API 키  ({status})").pack(pady=(15, 5))

        key_entry = tk.Entry(win, width=45, show="*")
        key_entry.pack(pady=5)
        key_entry.focus_set()

        def paste_clipboard(_event=None):
            try:
                text = win.clipboard_get().strip()
            except tk.TclError:
                return "break"  # 클립보드 비어있음
            key_entry.delete(0, tk.END)
            key_entry.insert(0, text)
            return "break"

        def on_command_key(event):
            """Cmd+V/C/A/X 처리 — 한글 입력기에서는 keysym이 'v'가 아니라
            'ㅍ'으로 들어와 일반 <Command-v> 바인딩이 매치되지 않으므로,
            keysym(영/한) + 물리 keycode 둘 다로 판정한다."""
            key = (event.keysym or "").lower()
            code = event.keycode
            if key in ("v", "ㅍ") or code == 9:        # V (kVK_ANSI_V)
                return paste_clipboard()
            if key in ("a", "ㅁ") or code == 0:        # A: 전체 선택
                key_entry.select_range(0, tk.END)
                key_entry.icursor(tk.END)
                return "break"
            if key in ("c", "ㅊ", "x", "ㅌ") or code in (8, 7):  # C/X: 복사·잘라내기
                try:
                    selected = key_entry.selection_get()
                except tk.TclError:
                    return "break"
                win.clipboard_clear()
                win.clipboard_append(selected)
                if key in ("x", "ㅌ") or code == 7:
                    key_entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
                return "break"
            return None

        key_entry.bind("<Command-KeyPress>", on_command_key)
        key_entry.bind("<Control-KeyPress>", on_command_key)

        # 핵심: 메뉴 액셀러레이터 — macOS에서 Cmd+V는 한글 입력기(IME)가
        # 키 이벤트를 삼켜 Tk 바인딩에 도달하지 않는다(Tk<=8.6.12 버그).
        # 메뉴의 key equivalent는 IME 이전(NSMenu 레벨)에서 처리되므로
        # 편집 메뉴를 달아야 입력기와 무관하게 단축키가 동작한다.
        def select_all():
            key_entry.select_range(0, tk.END)
            key_entry.icursor(tk.END)

        def copy_selection():
            try:
                selected = key_entry.selection_get()
            except tk.TclError:
                return
            win.clipboard_clear()
            win.clipboard_append(selected)

        menubar = tk.Menu(win)
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="붙여넣기", accelerator="Command-V",
                              command=paste_clipboard)
        edit_menu.add_command(label="복사", accelerator="Command-C",
                              command=copy_selection)
        edit_menu.add_command(label="전체 선택", accelerator="Command-A",
                              command=select_all)
        menubar.add_cascade(label="편집", menu=edit_menu)
        win.config(menu=menubar)

        # 테스트/디버깅용 핸들
        self._settings_entry = key_entry
        self._settings_paste = paste_clipboard
        self._settings_cmdkey = on_command_key

        # ---- 기본 저장 경로 설정 ----
        DEFAULT_DIR_TEXT = "(기본값: ~/Downloads)"
        current_dir = load_setting("output_dir")
        dir_var = tk.StringVar(value=current_dir or DEFAULT_DIR_TEXT)
        tk.Label(win, text="변환 결과 기본 저장 경로").pack(pady=(15, 5))
        dir_row = tk.Frame(win)
        dir_row.pack(pady=5)
        dir_label = tk.Label(
            dir_row, textvariable=dir_var, width=32, anchor="w", relief="sunken"
        )
        dir_label.pack(side="left", padx=(0, 5))

        def choose_dir():
            initial = dir_var.get()
            selected = filedialog.askdirectory(
                parent=win,
                title="기본 저장 경로 선택",
                initialdir=initial if os.path.isdir(initial) else os.path.expanduser("~"),
            )
            if selected:
                dir_var.set(selected)

        def reset_dir():
            dir_var.set(DEFAULT_DIR_TEXT)

        tk.Button(dir_row, text="폴더 선택", command=choose_dir).pack(side="left")
        tk.Button(dir_row, text="기본값", command=reset_dir).pack(side="left", padx=(5, 0))
        self._settings_dir_var = dir_var  # 테스트/디버깅용 핸들
        self._settings_dir_default_text = DEFAULT_DIR_TEXT

        def save():
            api_key = key_entry.get().strip()
            if api_key:  # 비워두면 기존 키 유지
                save_api_key(api_key)
            chosen = dir_var.get().strip()
            save_setting("output_dir", None if chosen in ("", DEFAULT_DIR_TEXT) else chosen)
            messagebox.showinfo("설정", "설정이 저장되었습니다.", parent=win)
            win.destroy()

        btn_row = tk.Frame(win)
        btn_row.pack(pady=10)
        tk.Button(btn_row, text="저장", command=save, width=10).pack(side="left", padx=5)
        tk.Button(btn_row, text="취소", command=win.destroy, width=10).pack(side="left", padx=5)

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

            # AI 사용인데 API 키가 없으면 시작 전에 에러로 중단 (설정으로 안내)
            if self.use_ai.get():
                api_key = load_api_key()
                if not api_key:
                    logging.warning("변환 중단: AI 사용 ON 상태에서 API 키 미등록")
                    messagebox.showerror(
                        "API 키 필요",
                        "AI 사용이 켜져 있지만 OpenAI API 키가 등록되지 않았습니다.\n"
                        "'설정' 버튼에서 API 키를 먼저 등록해주세요.",
                    )
                    return

            logging.info(
                "변환 시작: %s (AI %s)",
                self.selected_file_path,
                "ON" if self.use_ai.get() else "OFF",
            )
            # import file and convert to text
            text_list = import_file_to_text(self.selected_file_path)

            if self.use_ai.get():
                dialogue_text = extract_dialogue_ai(
                    text_list, self.selected_file_path, api_key
                )                                                    # AI 분류 추출
                converted_data = self._request_to_ai(dialogue_text)  # 기존 20자 분할
            else:
                speaker_and_dialogue_data = extract_speaker_and_dialogue(
                    text_list, self.selected_file_path
                )
                converted_data = data_processing(
                    "\n".join(speaker_and_dialogue_data)
                )

            # save to word file (설정된 저장 폴더, 없으면 기본 ~/Downloads)
            output_dir = load_setting("output_dir")
            file_name = os.path.basename(self.selected_file_path)
            save_to_word_file(converted_data, file_name + "_converted", output_dir=output_dir)
            shown_dir = output_dir if output_dir else "~/Downloads"
            self._saved_file_lable.config(
                text=f"저장된 파일 경로: {os.path.join(shown_dir, file_name + '_converted.docx')}"
            )

        except Exception as e:
            logging.exception("convert_file 실패")  # traceback 포함 로그
            messagebox.showerror("Error", str(e))

    def _request_to_ai(self, processed_data: str):
        # 긴 텍스트를 일정 크기(chunk_size)로 나누는 작업
        text_chunks = [
            processed_data[i: i + CHUNK_SIZE]
            for i in range(0, len(processed_data), CHUNK_SIZE)
        ]
        logging.info("20자 분할 요청: %d자 → %d청크", len(processed_data), len(text_chunks))

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
            except Exception:
                logging.exception("20자 분할 청크 %d 처리 실패", index)
                messagebox.showerror("Error", f"청크 {index} 처리 실패")
                # 청크들을 순서대로 합침
        return "\n".join(chunk for chunk in converted_data_chunks if chunk is not None)

    def _process_chunk(self, chunk, index, total_length, text_chunks):
        """단일 청크를 처리하는 메서드"""
        processed_chunk = data_processing(chunk)
        if self.use_ai:
            logging.info("20자 분할 청크 %d/%d 처리 중", index + 1, len(text_chunks))
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


def _report_tk_exception(exc, val, tb):
    """tkinter 콜백 안의 미처리 예외도 로그에 남긴다."""
    logging.error("GUI 콜백 예외", exc_info=(exc, val, tb))
    messagebox.showerror("Error", str(val))


if __name__ == "__main__":
    log_path = setup_logging()

    root = tk.Tk()
    root.title("Script Shaper")
    root.geometry("800x400")
    root.report_callback_exception = _report_tk_exception

    app = FileSelector(root)
    root.mainloop()
