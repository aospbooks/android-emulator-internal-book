"""Build nested EPUB Table of Contents from MkDocs nav config."""

from ebooklib import epub


def _src_to_epub_filename(src: str) -> str:
    """Convert MkDocs source path to EPUB chapter filename."""
    return src.replace(".md", ".xhtml")


def build_toc(nav: list, chapters: dict) -> list:
    """Build ebooklib ToC structure from MkDocs nav config.

    Args:
        nav: The 'nav' list from mkdocs.yml config.
        chapters: Dict mapping src_path -> EpubHtml item.

    Returns:
        List suitable for epub.Book.toc — mix of Link and (Section, [children]).
    """
    toc = []
    for entry in nav:
        if isinstance(entry, dict):
            for title, value in entry.items():
                if isinstance(value, str):
                    fname = _src_to_epub_filename(value)
                    toc.append(epub.Link(fname, title, fname))
                elif isinstance(value, list):
                    children = _build_children(value, chapters)
                    section = epub.Section(title)
                    toc.append((section, children))
        elif isinstance(entry, str):
            fname = _src_to_epub_filename(entry)
            toc.append(epub.Link(fname, entry, fname))
    return toc


def _build_children(items: list, chapters: dict) -> list:
    """Recursively build child ToC entries."""
    children = []
    for item in items:
        if isinstance(item, dict):
            for title, value in item.items():
                if isinstance(value, str):
                    fname = _src_to_epub_filename(value)
                    children.append(epub.Link(fname, title, fname))
                elif isinstance(value, list):
                    sub_children = _build_children(value, chapters)
                    section = epub.Section(title)
                    children.append((section, sub_children))
    return children


def build_spine_order(nav: list) -> list[str]:
    """Extract flat reading order (list of src paths) from nav config."""
    order = []
    for entry in nav:
        if isinstance(entry, dict):
            for _, value in entry.items():
                if isinstance(value, str):
                    order.append(value)
                elif isinstance(value, list):
                    order.extend(_extract_sources(value))
        elif isinstance(entry, str):
            order.append(entry)
    return order


def _extract_sources(items: list) -> list[str]:
    """Recursively extract source paths from nav items."""
    sources = []
    for item in items:
        if isinstance(item, dict):
            for _, value in item.items():
                if isinstance(value, str):
                    sources.append(value)
                elif isinstance(value, list):
                    sources.extend(_extract_sources(value))
        elif isinstance(item, str):
            sources.append(item)
    return sources
