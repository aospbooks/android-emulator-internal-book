"""Tests for mkdocs_mermaid_renderer."""

import hashlib
from pathlib import Path

from mkdocs_mermaid_renderer.renderer import MermaidRenderer, replace_mermaid_blocks, _hash_code


def test_hash_code_deterministic():
    assert _hash_code("graph TD; A-->B") == _hash_code("graph TD; A-->B")


def test_hash_code_differs():
    assert _hash_code("graph TD; A-->B") != _hash_code("graph LR; A-->B")


def test_queue_skips_cached(tmp_path):
    renderer = MermaidRenderer(tmp_path)
    code = "graph TD; A-->B"
    h = _hash_code(code)
    (tmp_path / f"{h}.svg").write_text("<svg>cached</svg>")
    renderer.queue(code)
    assert len(renderer._queue) == 0


def test_queue_adds_uncached(tmp_path):
    renderer = MermaidRenderer(tmp_path)
    renderer.queue("graph TD; A-->B")
    assert len(renderer._queue) == 1


def test_get_svg_returns_none_when_not_cached(tmp_path):
    renderer = MermaidRenderer(tmp_path)
    assert renderer.get_svg("graph TD; A-->B") is None


def test_get_svg_returns_cached(tmp_path):
    renderer = MermaidRenderer(tmp_path)
    code = "graph TD; A-->B"
    h = _hash_code(code)
    (tmp_path / f"{h}.svg").write_text("<svg>test</svg>")
    assert renderer.get_svg(code) == "<svg>test</svg>"


def test_replace_mermaid_blocks_substitutes(tmp_path):
    code = "graph TD; A-->B"
    h = _hash_code(code)
    (tmp_path / f"{h}.svg").write_text("<svg>replaced</svg>")
    html = f'<pre class="mermaid"><code>{code}</code></pre>'
    result = replace_mermaid_blocks(html, tmp_path)
    assert '<div class="mermaid-svg"><svg>replaced</svg></div>' in result


def test_replace_mermaid_blocks_preserves_uncached(tmp_path):
    html = '<pre class="mermaid"><code>graph TD; X-->Y</code></pre>'
    result = replace_mermaid_blocks(html, tmp_path)
    assert result == html
