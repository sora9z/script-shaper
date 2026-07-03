import os

from docx import Document

from utils.save_to_word import save_to_word_file


def test_save_to_word_respects_output_dir(tmp_path):
    save_to_word_file("첫 줄.\n둘째 줄.", "결과", output_dir=str(tmp_path))
    out = tmp_path / "결과.docx"
    assert out.exists()
    paras = [p.text for p in Document(str(out)).paragraphs if p.text.strip()]
    assert paras == ["첫 줄.", "둘째 줄."]


def test_save_to_word_default_is_downloads(monkeypatch, tmp_path):
    # 기본값(output_dir 미지정)은 ~/Downloads — GUI 동작 불변 확인 (홈을 tmp로 속임)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    save_to_word_file("내용.", "기본저장")
    assert (tmp_path / "Downloads" / "기본저장.docx").exists()
