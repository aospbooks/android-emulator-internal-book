"""MkDocs plugin: fast PDF export with pre-rendered Mermaid SVGs.

Strategy:
  1. on_page_markdown  — extract mermaid code blocks, hash them, queue for rendering
  2. on_env            — batch-render all uncached mermaid diagrams to SVG via Playwright
  3. on_post_page      — clone HTML, replace mermaid blocks with cached SVGs, queue for PDF
                         also extract headings for Table of Contents
  4. on_post_build     — render queued pages to PDF concurrently, generate ToC,
                         aggregate: cover + ToC + content pages
"""

import asyncio
import logging
import re
import time
from pathlib import Path

from mkdocs.config import config_options as opt
from mkdocs.plugins import BasePlugin
from mkdocs_mermaid_renderer import MermaidRenderer, replace_mermaid_blocks

log = logging.getLogger("mkdocs.plugins.pdf-generate")

# ---------------------------------------------------------------------------
# PDF-specific CSS injected into each page before rendering
# ---------------------------------------------------------------------------

PDF_CSS = """\
@page { size: A4; margin: 1.8cm 1.5cm; }

/* Hide site chrome and navigation */
.md-header, .md-footer, .md-footer-nav, .md-sidebar, .md-tabs,
.md-dialog, .md-top, #mermaid-zoom-overlay,
.mermaid-zoom-toolbar, .md-clipboard,
.md-header-nav, .md-skip,
nav.md-footer__inner { display: none !important; }
a.md-skip { display: none !important; }
.md-content { margin: 0 !important; max-width: 100% !important; }
.md-main__inner { max-width: 100% !important; }
.md-typeset { font-size: 11pt; }

/* Page breaks */
h1 { break-before: page; page-break-before: always; }
h2, h3, h4 { break-after: avoid; page-break-after: avoid; }
pre, .highlight, table, .admonition, details {
  break-inside: avoid; page-break-inside: avoid;
}

/* Mermaid SVGs */
.mermaid-svg {
  break-inside: avoid; page-break-inside: avoid;
  text-align: center; margin: 1em 0;
}
.mermaid-svg svg {
  max-width: 100% !important; max-height: 24cm !important;
  height: auto !important;
}

/* Tables — visible borders and lines */
.md-typeset table:not([class]),
.md-typeset table {
  border-collapse: collapse !important;
  border: 1px solid #616161 !important;
  width: 100%;
}
.md-typeset table th,
.md-typeset table td {
  border: 1px solid #9e9e9e !important;
  padding: 6px 10px !important;
}
.md-typeset table th {
  background-color: #e8f5e9 !important;
  font-weight: 600;
  border-bottom: 2px solid #616161 !important;
}
.md-typeset table tr:nth-child(even) td {
  background-color: #fafafa !important;
}

/* Code blocks — distinct background */
.md-typeset pre,
.highlight pre,
.md-typeset .highlight {
  background-color: #f5f5f5 !important;
  border: 1px solid #e0e0e0 !important;
  border-radius: 4px !important;
  padding: 12px !important;
}
.md-typeset code {
  background-color: #f5f5f5 !important;
}
.md-typeset :not(pre) > code {
  background-color: #eeeeee !important;
  border: 1px solid #e0e0e0 !important;
  padding: 1px 4px !important;
  border-radius: 3px !important;
}

/* Cover page */
.pdf-cover-page {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: 100vh; text-align: center;
  background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 40%, #43a047 100%);
  color: white; font-family: 'Roboto', sans-serif;
  page-break-after: always;
}
.pdf-cover-page h1 {
  font-size: 3em; font-weight: 700; letter-spacing: -0.02em;
  margin: 0.3em 0; break-before: auto; page-break-before: auto;
  color: white;
}
.pdf-cover-page h2 {
  font-size: 1.5em; font-weight: 300; opacity: 0.9; margin: 0;
  color: white;
}
.pdf-cover-page hr {
  width: 120px; height: 3px; background: rgba(255,255,255,0.5);
  border: none; margin: 2em 0;
}
.pdf-cover-page .meta {
  font-size: 0.95em; opacity: 0.7; margin-top: 1em;
}
"""

# Minimum text length to include a page (filters "Skip to content" pages)
_MIN_CONTENT_LENGTH = 200


class PdfGeneratePlugin(BasePlugin):
    config_scheme = (
        ("enabled", opt.Type(bool, default=False)),
        ("concurrency", opt.Type(int, default=8)),
        ("output", opt.Type(str, default="book.pdf")),
        ("cover", opt.Type(str, default="")),
        ("timeout", opt.Type(int, default=30000)),
        ("stylesheets", opt.Type(list, default=[])),
    )

    # ── lifecycle ──

    def on_config(self, config, **kwargs):
        if not self.config["enabled"]:
            return
        self._config_dir = Path(config["config_file_path"]).parent
        self._cache_dir = self._config_dir / ".mermaid-cache"
        self._cache_dir.mkdir(exist_ok=True)
        self._renderer = MermaidRenderer(self._cache_dir)
        self._pdf_queue = []     # [(page, html, pdf_path), ...]
        self._toc_entries = []   # [(level, title, page_src), ...]
        self._extra_css = ""
        for css_path in self.config["stylesheets"]:
            p = self._config_dir / css_path
            if p.exists():
                self._extra_css += p.read_text() + "\n"
        log.info("[pdf] Plugin enabled (concurrency=%d)", self.config["concurrency"])

    def on_page_markdown(self, markdown, page, config, files, **kwargs):
        if not self.config["enabled"]:
            return markdown
        for m in re.finditer(r"```mermaid\n(.*?)\n```", markdown, re.DOTALL):
            self._renderer.queue(m.group(1).strip())
        return markdown

    def on_env(self, env, config, files, **kwargs):
        if not self.config["enabled"]:
            return
        self._renderer.render_batch()

    def on_post_page(self, output, page, config, **kwargs):
        if not self.config["enabled"]:
            return output
        # Skip pages with no real content (e.g. index with only "Skip to content")
        text = re.sub(r"<[^>]+>", "", output)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < _MIN_CONTENT_LENGTH:
            log.info("[pdf] Skipping empty page: %s", page.file.src_path)
            return output

        # Extract headings for Table of Contents
        self._extract_headings(output, page)

        pdf_html = self._prepare_pdf_html(output, config)
        dest = page.file.dest_path.replace(".html", ".pdf")
        pdf_path = Path(config["site_dir"]) / dest
        self._pdf_queue.append((page, pdf_html, pdf_path))
        return output  # web version unchanged

    def on_post_build(self, config, **kwargs):
        if not self.config["enabled"]:
            return
        if not self._pdf_queue:
            return
        t0 = time.monotonic()
        asyncio.run(self._render_pdfs())
        render_time = time.monotonic() - t0
        log.info("[pdf] Rendered %d pages in %.1fs", len(self._pdf_queue), render_time)
        self._aggregate_pdfs(config)

    # ── heading extraction for ToC ──

    def _extract_headings(self, html, page):
        """Extract h1, h2, h3 headings from rendered HTML for ToC."""
        for m in re.finditer(r"<h([123])[^>]*>(.*?)</h\1>", html, re.DOTALL):
            level = int(m.group(1))
            # Strip HTML tags, permalink anchors (¶), and whitespace
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            title = title.replace("¶", "").replace("&para;", "").replace("&#182;", "").strip()
            # Skip empty or anchor-only headings
            if title and len(title) > 1:
                self._toc_entries.append((level, title, page.file.src_path))

    # ── HTML preprocessing for PDF ──

    def _prepare_pdf_html(self, html, config):
        """Transform rendered HTML for PDF: inject SVGs, strip nav, add CSS."""
        html = replace_mermaid_blocks(html, self._cache_dir)
        html = html.replace("<details", "<details open")
        # Strip footer navigation ("Proceed to Chapter X" / Previous/Next links)
        html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL)
        html = re.sub(r"<nav[^>]*class=\"[^\"]*md-footer[^\"]*\"[^>]*>.*?</nav>", "", html, flags=re.DOTALL)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        css = f"<style>{PDF_CSS}\n{self._extra_css}</style>"
        html = html.replace("</head>", f"{css}\n</head>")
        return html

    # ── PDF rendering ──

    async def _render_pdfs(self):
        """Render all queued pages to PDF concurrently using Playwright async."""
        from playwright.async_api import async_playwright

        total = len(self._pdf_queue)
        log.info("[pdf] Rendering %d pages to PDF (concurrency=%d)...", total, self.config["concurrency"])

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                ],
            )

            sem = asyncio.Semaphore(self.config["concurrency"])
            count = [0]

            async def render_one(page_data, html, pdf_path):
                async with sem:
                    pdf_path.parent.mkdir(parents=True, exist_ok=True)
                    bp = await browser.new_page()
                    try:
                        await bp.set_content(html, wait_until="load", timeout=self.config["timeout"])
                        await bp.pdf(
                            path=str(pdf_path),
                            format="A4",
                            print_background=True,
                            prefer_css_page_size=True,
                        )
                    except Exception as e:
                        log.warning("[pdf] Failed: %s — %s", page_data.file.src_path, str(e)[:120])
                    finally:
                        await bp.close()
                    count[0] += 1
                    if count[0] % 10 == 0 or count[0] == total:
                        log.info("[pdf]   ...%d/%d pages", count[0], total)

            tasks = [render_one(p, h, pp) for p, h, pp in self._pdf_queue]
            await asyncio.gather(*tasks)
            await browser.close()

    # ── Table of Contents generation ──

    def _render_toc_pdf(self, config):
        """Generate a Table of Contents page from collected headings."""
        from playwright.sync_api import sync_playwright

        if not self._toc_entries:
            return None

        toc_pdf = Path(config["site_dir"]) / "_toc.pdf"

        # Build ToC HTML
        items = []
        for level, title, src in self._toc_entries:
            if level == 1:
                items.append(
                    f'<div class="toc-h1">{_escape_html(title)}</div>'
                )
            elif level == 2:
                items.append(
                    f'<div class="toc-h2">{_escape_html(title)}</div>'
                )
            else:
                items.append(
                    f'<div class="toc-h3">{_escape_html(title)}</div>'
                )

        toc_body = "\n".join(items)

        html = f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 1.8cm 1.5cm; }}
body {{
  font-family: 'Roboto', 'Segoe UI', sans-serif;
  color: #1b1b1b; font-size: 10pt; line-height: 1.5;
}}
.toc-title {{
  font-size: 2em; font-weight: 700; color: #1b5e20;
  margin-bottom: 0.8em; padding-bottom: 0.3em;
  border-bottom: 3px solid #4CAF50;
}}
.toc-h1 {{
  font-size: 1.05em; font-weight: 700; color: #1b5e20;
  margin: 0.6em 0 0.15em 0; padding-top: 0.3em;
  border-top: 1px solid #e0e0e0;
}}
.toc-h1:first-of-type {{ border-top: none; padding-top: 0; }}
.toc-h2 {{
  font-size: 0.95em; font-weight: 500; color: #333;
  margin: 0.15em 0 0.1em 1.5em;
}}
.toc-h3 {{
  font-size: 0.85em; font-weight: 400; color: #666;
  margin: 0.08em 0 0.08em 3em;
}}
</style>
</head>
<body>
<div class="toc-title">Table of Contents</div>
{toc_body}
</body></html>"""

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(path=str(toc_pdf), format="A4", print_background=True)
            page.close()
            browser.close()

        log.info("[pdf] Generated Table of Contents (%d entries)", len(self._toc_entries))
        return toc_pdf

    # ── PDF aggregation ──

    def _aggregate_pdfs(self, config):
        """Merge: cover + ToC + content pages into single PDF."""
        from pypdf import PdfWriter

        output_path = Path(config["site_dir"]) / self.config["output"]
        log.info("[pdf] Aggregating %d pages into %s...", len(self._pdf_queue), self.config["output"])
        t0 = time.monotonic()

        writer = PdfWriter()

        # 1. Cover page
        cover = self.config.get("cover", "")
        if cover:
            cover_pdf = self._render_cover_page(config, cover)
            if cover_pdf and cover_pdf.exists():
                writer.append(str(cover_pdf))

        # 2. Table of Contents
        toc_pdf = self._render_toc_pdf(config)
        if toc_pdf and toc_pdf.exists():
            writer.append(str(toc_pdf))

        # 3. Content pages
        for i, (page, _, pdf_path) in enumerate(self._pdf_queue):
            if pdf_path.exists():
                try:
                    writer.append(str(pdf_path))
                except Exception as e:
                    log.warning("[pdf] Skip merge: %s — %s", page.file.src_path, str(e)[:80])
            if (i + 1) % 20 == 0:
                log.info("[pdf]   ...merged %d/%d", i + 1, len(self._pdf_queue))

        writer.write(str(output_path))
        writer.close()

        elapsed = time.monotonic() - t0
        size_mb = output_path.stat().st_size / 1024 / 1024
        log.info("[pdf] Done: %s (%.1f MB, %.1fs)", output_path.name, size_mb, elapsed)

    def _render_cover_page(self, config, cover_source):
        """Render a cover page to PDF."""
        from playwright.sync_api import sync_playwright

        cover_pdf = Path(config["site_dir"]) / "_cover.pdf"

        cover_file = Path(self._config_dir) / cover_source
        if not cover_file.exists():
            log.warning("[pdf] Cover file not found: %s", cover_source)
            return None

        if cover_source.endswith(".svg"):
            svg_data = cover_file.read_text()
            html = f"""\
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 0; }}
html, body {{ margin: 0; padding: 0; width: 210mm; height: 297mm; overflow: hidden; }}
body {{ display: flex; align-items: center; justify-content: center; background: #fff; }}
svg {{ max-width: 210mm; max-height: 297mm; width: auto; height: auto; }}
</style>
</head><body>
{svg_data}
</body></html>"""
        elif cover_source.endswith(".j2"):
            from jinja2 import Environment, FileSystemLoader
            env = Environment(loader=FileSystemLoader(str(cover_file.parent)))
            tmpl = env.get_template(cover_file.name)
            html = tmpl.render(config=config)
            html = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{html}</body></html>"
        else:
            site_name = config.get("site_name", "Book")
            site_desc = config.get("site_description", "")
            html = f"""\
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{PDF_CSS}</style>
</head><body>
<div class="pdf-cover-page">
  <h1>{_escape_html(site_name)}</h1>
  <hr>
  <h2>{_escape_html(site_desc)}</h2>
</div>
</body></html>"""

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(path=str(cover_pdf), format="A4", print_background=True)
            page.close()
            browser.close()

        return cover_pdf


def _escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
