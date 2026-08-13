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
  // Keep in sync with stylesheets/mermaid-theme.css and
  // javascripts/mermaid-theme.js (site skin, light palette): blue-50 node
  // cards with primary-blue borders, blue-tinted cluster washes, uppercase
  // mono zone labels, blue mono edge annotations.
  themeVariables: {
    primaryColor: '#E3F2FD',
    primaryTextColor: '#212121',
    primaryBorderColor: '#1976d2',
    lineColor: '#546e7a',
    actorLineColor: '#a9c3e4',
    secondaryColor: '#BBDEFB',
    tertiaryColor: '#F7FAFD',
    clusterBkg: '#F7FAFD',
    clusterBorder: '#D6E4F5',
    noteBkgColor: '#BBDEFB',
    noteTextColor: '#1b1b1b',
    fontFamily: 'Roboto, Helvetica, Arial, sans-serif'
  },
  themeCSS: [
    'foreignObject{overflow:visible}',
    '.node rect{rx:6px;ry:6px;stroke-width:1px}',
    '.nodeLabel{font-size:14px}',
    '.cluster rect{rx:8px;ry:8px}',
    '.cluster-label .nodeLabel{font-family:"Roboto Mono",monospace;' +
      'font-size:10.5px;font-weight:500;letter-spacing:.14em;' +
      'text-transform:uppercase;color:rgba(21,101,192,0.75)!important}',
    '.edgePath .path,.flowchart-link{stroke-width:1.1px}',
    '.edgeLabel .nodeLabel,span.edgeLabel{font-family:"Roboto Mono",monospace;' +
      'font-size:11.5px;color:#1565c0!important}',
    '.actor{rx:6px;stroke-width:1px}',
    'text.actor>tspan{font-size:14px}',
    '.messageText{font-size:12.5px;font-family:"Roboto Mono",monospace!important}',
    '.noteText>tspan,.labelText>tspan,.loopText>tspan{font-size:12.5px}',
    '.activation0,.activation1,.activation2{fill:#E8F1FB;stroke:#546e7a;stroke-width:0.8px}'
  ].join('')
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
