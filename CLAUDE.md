# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ScriptShaper (자막제작자를 위한 대본 변환 프로젝트) is a Korean-language Tkinter desktop app for subtitle creators. It reads a script/document, extracts the dialogue lines (dropping speaker names and stage directions), optionally calls OpenAI to re-wrap the text into ≤20-character subtitle lines, and writes the result to a Word document in `~/Downloads`. The UI, code comments, and commit messages are all in Korean.

The app targets **macOS**: it is distributed as a single PyInstaller binary built by CI, and output/settings paths are hardcoded to `~/Downloads`.

## Core Architecture

### Pipeline (`main.py` → `FileSelector.convert_file`)
`import_file_to_text` → `extract_speaker_and_dialogue` → `data_processing` → (optional AI) → `save_to_word_file`

Each stage lives in `utils/` and the GUI orchestrates them. The only stateful object is `FileSelector`; everything in `utils/` is plain functions.

### Dialogue detection is the core domain logic (`utils/extract_speaker_and_dialogue.py`)
This is where most recent work has gone and the part most worth reading before changing behavior. For each input line it decides "is this dialogue?" via a **first-match-wins cascade**:
1. Speaker-pattern regexes from `constants.py` (`화자명: 대사`, `화자명␣␣␣대사`)
2. Ends with dialogue punctuation (`! ? … ... ~ , ; "`)
3. Ends with a **multi-char** Korean colloquial ending (`요`, `습니까`, `거야`, `잖아요`, …) — checked before one-char endings on purpose
4. Ends with a **single-char** ending (`다`, `네`, `해`, …), but only for text ≥ 2 chars
5. Contains a multi-char colloquial ending **anywhere mid-sentence**

Before steps 2–5 the line is stripped of trailing `()`/`[]`/`{}` groups (and trailing unclosed brackets), and a trailing `.` is ignored, so `안녕하세요.` matches the `요` ending. The authoritative human-readable spec for these rules is the **"대사 인식 조건"** section of `README.md` — keep it and this code in sync when editing endings. Ending lists (`KOREAN_ONE_CHAR_ENDINGS`, `KOREAN_MULTI_CHAR_ENDINGS`) are inline in this file, **not** in `constants.py`.

**`.xlsx` files bypass detection entirely** — `extract_speaker_and_dialogue` returns the raw line list for Excel, on the assumption each cell is already one dialogue line.

When "AI 사용" is ON, `main.py` routes extraction through `utils/openai_extract.py:extract_dialogue_ai` instead: an OpenAI structured-output classifier (`gpt-5.4`) labels each line dialogue/narration/scene/other and returns the bare speaker name; `assemble_dialogue` keeps only dialogue, slices the speaker prefix via `remove_speaker_prefix`, and reuses `remove_inline_directions`. The cascade above is the AI-OFF fallback (also used per-line for any id the model drops). Run headless via `convert_cli.py`.

### Text processing (`utils/data_processing.py`)
Removes speaker prefixes (same `SPEAKER_DIALOGUE_REGEX_LIST`) and strips bracketed stage directions. Note the trailing-period-insertion block is **commented out** despite the docstring describing it. When AI is enabled this function runs twice on the same text (once on the full text in `convert_file`, again per-chunk in `_process_chunk`).

### AI enhancement (`utils/openai.py`)
Single function `request_to_openai(api_key, content)`: hardcoded `model="gpt-5.4"`, `temperature=0.5`, with a long Korean prompt instructing the model to split into ≤20-char lines **without altering wording**. `main.py` shards the text into raw `CHUNK_SIZE = 4000`-char slices (which can cut mid-sentence) and runs up to 5 concurrent calls via `ThreadPoolExecutor`, reassembling by original index.

## Important gotchas

- **Advertised formats ≠ implemented formats.** The file picker, README, and overview list Word/Excel/CSV/PDF/HWP/TXT, but `utils/file_reader_list.py` only implements `.docx` and `.xlsx`/`.xls`. `.doc` raises a "not supported" error; selecting a `.pdf`/`.csv`/`.txt`/`.hwp` falls through to `read_file` returning `None`, which then errors downstream. Implementing a new format means adding a branch in `read_file`. `pyhwp` / `pdfminer.six` are installed but unused.
- **`.docx` reader replaces tabs with 4 spaces on purpose** — to make the `화자명␣␣␣대사` (3+ spaces) speaker regex match.
- **Settings and all output live in `~/Downloads`**, not the project dir: API key in `~/Downloads/settings.json` (`utils/json_service.py`), converted file as `<name>_converted.docx` (`utils/save_to_word.py`). If `settings.json` is missing, the GUI prompts for the key and writes it there.

## Development commands

```bash
pipenv install        # deps (Python 3.11)
pipenv shell
python main.py        # run the GUI
pyinstaller main.spec # local one-file build → dist/
```

There is **no automated test suite**; `data/test.docx` and `data/test.xlsx` are sample inputs for manual GUI testing, not unit tests.

## CI / release

Pushing to `main` triggers `.github/workflows/release.yml` on `macos-latest`: it builds with `pyinstaller --onefile main.py` (note: CI builds from `main.py` directly, **not** `main.spec`), then creates a GitHub Release whose tag comes from `git describe --tags --abbrev=0` (falling back to `v1.0.5`) and attaches the binary as `script-shaper`. Bumping the release version means creating/pushing a new git tag.
