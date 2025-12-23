# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ScriptShaper is a Python GUI application for subtitle creators that converts scripts and documents into subtitle-friendly format. It processes various file types (Word, Excel, CSV, PDF, HWP) to extract speaker names and dialogue, then optionally uses OpenAI's API to split text into subtitle segments.

## Core Architecture

### Main Application Flow
- `main.py`: Tkinter GUI application with `FileSelector` class as the main interface
- File processing pipeline: Import → Extract → Process → Optional AI → Save

### Processing Pipeline
1. **File Import** (`utils/import_file_to_text.py`): Converts various file formats to text
2. **Dialogue Extraction** (`utils/extract_speaker_and_dialogue.py`): Uses regex patterns from `constants.py` to identify dialogue lines
3. **Text Processing** (`utils/data_processing.py`): Removes speaker names and stage directions (parentheses/brackets)
4. **AI Enhancement** (`utils/openai.py`): Optional OpenAI integration to split text into 20-character subtitle segments
5. **Output** (`utils/save_to_word.py`): Saves processed text to Word document

### Key Components
- **Regex-based dialogue detection**: Uses `SPEAKER_DIALOGUE_REGEX_LIST` in `constants.py` to identify speaker patterns like "화자명: 대사" and "화자명    대사"
- **Parallel AI processing**: Chunks large text (4000 char chunks) for concurrent OpenAI API calls with ThreadPoolExecutor
- **Settings management**: API keys stored in `~/Downloads/settings.json` via `json_service.py`

## Development Commands

### Environment Setup
```bash
# Install dependencies
pipenv install

# Activate virtual environment
pipenv shell

# Run application
python main.py
```

### Build Distribution
```bash
# Build standalone executable (configured in main.spec)
pyinstaller main.spec
```

## File Structure Notes

- `utils/` contains all processing modules
- `data/` contains test files (test.docx, test.xlsx)
- `dist/` and `build/` are PyInstaller output directories
- Settings stored in user's Downloads folder, not in project directory

## AI Integration

The OpenAI integration splits Korean text into subtitle-friendly segments with these constraints:
- Maximum 20 characters per line
- Preserves original text without modification
- Natural sentence breaking
- Uses GPT-4o model with temperature 0.5