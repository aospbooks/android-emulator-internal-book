"""Batch Mermaid-to-SVG renderer with file-based caching."""

import hashlib
import logging
import re
import time
from html import unescape
from pathlib import Path

log = logging.getLogger("mkdocs-mermaid-renderer")

MERMAID_TEMPLATE = """\
<!DOCTYPE html>
<html><head>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'loose',
  theme: 'base',
  themeVariables: {
    primaryColor: '#4CAF50',
    primaryTextColor: '#1b1b1b',
    primaryBorderColor: '#388E3C',
    lineColor: '#616161',
    secondaryColor: '#E8F5E9',
    tertiaryColor: '#F5F5F5',
    noteBkgColor: '#E8F5E9',
    noteTextColor: '#1b1b1b'
  }
});
var _c = 0;
window.renderDiagram = async function(code) {
  var id = 'mmd' + (_c++);
  var result = await mermaid.render(id, code);
  return result.svg;
};
window.mermaidReady = true;
</script>
</head><body></body></html>
"""


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()[:16]


class MermaidRenderer:
    """Batch Mermaid diagram renderer with file-based SVG cache."""

    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(exist_ok=True)
        self._queue: dict[str, str] = {}  # hash -> code

    def queue(self, code: str) -> None:
        """Queue a mermaid code block for rendering if not already cached."""
        h = _hash_code(code)
        if not (self._cache_dir / f"{h}.svg").exists():
            self._queue[h] = code

    def render_batch(self) -> None:
        """Render all queued diagrams to SVG via Playwright. Idempotent."""
        if not self._queue:
            return

        from playwright.sync_api import sync_playwright

        total = len(self._queue)
        log.info("Rendering %d uncached mermaid diagrams...", total)
        t0 = time.monotonic()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            page = browser.new_page()
            page.set_content(MERMAID_TEMPLATE)
            page.wait_for_function("window.mermaidReady === true", timeout=15000)

            rendered = 0
            for hash_id, code in self._queue.items():
                try:
                    svg = page.evaluate("code => window.renderDiagram(code)", code)
                    (self._cache_dir / f"{hash_id}.svg").write_text(svg)
                    rendered += 1
                except Exception as e:
                    log.warning("Mermaid failed [%s]: %s", hash_id[:8], str(e)[:120])
                if rendered % 100 == 0 and rendered > 0:
                    log.info("  ...%d/%d diagrams", rendered, total)

            browser.close()

        elapsed = time.monotonic() - t0
        log.info("Mermaid rendering done: %d/%d in %.1fs", rendered, total, elapsed)
        self._queue.clear()

    def get_svg(self, code: str) -> str | None:
        """Return cached SVG for a mermaid code block, or None."""
        h = _hash_code(code)
        svg_file = self._cache_dir / f"{h}.svg"
        if svg_file.exists():
            return svg_file.read_text()
        return None


def replace_mermaid_blocks(html: str, cache_dir: Path) -> str:
    """Replace <pre class="mermaid"> blocks in HTML with cached SVGs."""

    def _sub(m):
        raw = m.group(1)
        code = unescape(raw).strip()
        h = _hash_code(code)
        svg_file = cache_dir / f"{h}.svg"
        if svg_file.exists():
            svg = svg_file.read_text()
            return f'<div class="mermaid-svg">{svg}</div>'
        return m.group(0)

    html = re.sub(
        r'<pre[^>]*class="[^"]*mermaid[^"]*"[^>]*>\s*<code>(.*?)</code>\s*</pre>',
        _sub, html, flags=re.DOTALL,
    )
    html = re.sub(
        r'<pre[^>]*class="[^"]*mermaid[^"]*"[^>]*>(.*?)</pre>',
        _sub, html, flags=re.DOTALL,
    )
    return html
