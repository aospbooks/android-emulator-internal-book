"""Tests for EPUB ToC builder."""

from mkdocs_epub_generate.toc_builder import build_toc, build_spine_order


SAMPLE_NAV = [
    {"Introduction": "index.md"},
    {"Part I: Getting Started": [
        {"Frontmatter": "00-frontmatter.md"},
        {"1. Introduction": "01-introduction.md"},
    ]},
    {"Part II: Kernel & Boot": [
        {"4. Boot and Init": "04-boot-and-init.md"},
    ]},
]


def test_build_toc_returns_nested_structure():
    toc = build_toc(SAMPLE_NAV, {})
    assert len(toc) == 3


def test_build_toc_top_level_link():
    from ebooklib import epub
    toc = build_toc(SAMPLE_NAV, {})
    first = toc[0]
    assert isinstance(first, epub.Link)
    assert first.title == "Introduction"


def test_build_toc_part_has_children():
    toc = build_toc(SAMPLE_NAV, {})
    section_entry = toc[1]
    assert isinstance(section_entry, tuple)
    section, children = section_entry
    assert len(children) == 2


def test_build_spine_order():
    order = build_spine_order(SAMPLE_NAV)
    assert order == [
        "index.md",
        "00-frontmatter.md",
        "01-introduction.md",
        "04-boot-and-init.md",
    ]
