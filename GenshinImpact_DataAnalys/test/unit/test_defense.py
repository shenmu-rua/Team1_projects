"""报告删节与SVG内嵌的契约，只用合成文档。"""

from genshin_insight.defense import inline_svg, without_scope


def test_remove_only_scope_section_preserving_later_notes():
    report = (
        "# 分析\n\n主分析口径\n\n## 图表与结论\n\n"
        "### 来源对比\n\n![示意](Q01_数据集范围.png)\n\n"
        "### 分析结果\n\n![示意](A01_卡池.png)\n\n"
        "## 复现与保护\n\n保留这一段\n"
    )
    updated = without_scope(report)
    assert "Q01_" not in updated and "来源对比" not in updated
    assert "A01_卡池" in updated and "保留这一段" in updated and "主分析口径" in updated
    assert without_scope(updated) == updated


def test_inline_svg_ids_and_references_are_isolated(tmp_path):
    svg = tmp_path / "synthetic.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><defs><circle id="dot" r="2"/><clipPath id="clip"><rect width="5" height="5"/></clipPath></defs><g clip-path="url(#clip)"><use xlink:href="#dot"/><text>合成标签</text></g></svg>',
        encoding="utf-8",
    )
    a, b = inline_svg(svg, "a01-"), inline_svg(svg, "a02-")
    assert 'id="a01-clip"' in a and "url(#a01-clip)" in a
    assert 'id="a02-clip"' in b and "url(#a02-clip)" in b
    assert "url(#clip)" not in a + b
    assert 'xlink:href="#a01-dot"' in a and 'xlink:href="#a02-dot"' in b
