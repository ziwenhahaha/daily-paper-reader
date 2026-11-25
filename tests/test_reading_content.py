import importlib.util
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
spec = importlib.util.spec_from_file_location(
    "reading_generator", Path(__file__).resolve().parents[1] / "src/6.generate_docs.py"
)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def test_modern_paper_uses_daily_cards_and_preserves_route_and_notes(
    tmp_path, monkeypatch
):
    route = "20250910-20260909/2510.17595v1"
    path = tmp_path / (route + ".md")
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\ntitle: ATSP\nevidence: 原专题评审理由\nselection_source: long-range\n---\n\n## Abstract\nAbstract\n\n## 我的笔记\n不能删除\n"
    )
    paper = {
        "id": "2510.17595v1",
        "title": "ATSP",
        "abstract": "Abstract",
        "source": "arxiv",
        "selection_source": "long-range",
        "llm_tags": ["query:ATSP"],
        "pdf_url": "https://arxiv.org/pdf/2510.17595v1",
    }
    monkeypatch.setattr(gen, "create_llm_client", lambda: Mock(kwargs={}))
    translate = Mock(return_value=("中文标题", "中文摘要"))
    glance = Mock(
        return_value="\n".join(
            f"**{k}**：{v}"
            for k, v in {
                "TLDR": "完整速览摘要",
                "Motivation": "研究动机",
                "Method": "研究方法",
                "Result": "主要结果",
                "Conclusion": "研究结论",
                "Evidence": "非对称先验旅行商近似算法",
            }.items()
        )
    )
    deep = Mock(return_value="详细方法与证明总结\n（完）")
    monkeypatch.setattr(gen, "translate_title_and_abstract_to_zh", translate)
    monkeypatch.setattr(gen, "generate_glance_overview", glance)
    monkeypatch.setattr(gen, "generate_deep_summary", deep)
    monkeypatch.setattr(gen, "ensure_text_content", lambda *a: "fulltext " * 300)
    monkeypatch.setattr(gen, "maybe_generate_paper_media", lambda *a, **k: ([], []))
    for _ in range(2):
        actual, _ = gen.process_paper(
            paper,
            "deep",
            "20250910-20260909",
            str(tmp_path),
            route=route,
            require_complete=True,
        )
        assert actual == route
    text = path.read_text()
    meta = gen._parse_front_matter(text)
    assert meta["title_zh"] == "中文标题"
    assert meta["motivation"] == "研究动机"
    assert meta["tldr"] == "完整速览摘要"
    assert meta["evidence"] == "非对称先验旅行商近似算法"
    assert "## 摘要\n中文摘要" in text and "不能删除" in text
    assert "论文详细总结（自动生成）" in text
    translate.assert_called_once()
    glance.assert_called_once()
    deep.assert_called_once()


def test_route_escape_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        gen.process_paper(
            {"title": "x"}, "quick", "20260910", str(tmp_path), route="../escape"
        )


def test_missing_llm_content_fails_instead_of_publishing_placeholder(
    tmp_path, monkeypatch
):
    path = tmp_path / "paper.md"
    path.write_text(
        "---\ntitle: Test\nselection_source: long-range\n---\n\n## Abstract\ntext\n用户笔记"
    )
    monkeypatch.setattr(
        gen, "translate_title_and_abstract_to_zh", lambda *a, **k: ("", "")
    )
    monkeypatch.setattr(gen, "generate_glance_overview", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="未生成完整"):
        gen.ensure_reading_content(
            {"title": "Test", "abstract": "text", "selection_source": "long-range"},
            "quick",
            str(path),
            str(tmp_path / "paper.txt"),
            Mock(),
            require_complete=True,
        )
    assert "用户笔记" in path.read_text()
    assert "reading_section" not in path.read_text()
