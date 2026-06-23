"""MkDocs plugin: EPUB3 export with pre-rendered Mermaid SVGs.

Strategy:
  1. on_config        — initialize state, shared renderer
  2. on_page_markdown — queue mermaid code blocks for rendering
  3. on_env           — batch-render uncached mermaid diagrams
  4. on_post_page     — clean HTML, collect chapters and images
  5. on_post_build    — assemble EPUB: cover, ToC, chapters, images
"""

import logging
import mimetypes
import posixpath
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from ebooklib import epub
from mkdocs.config import config_options as opt
from mkdocs.plugins import BasePlugin
from mkdocs_mermaid_renderer import MermaidRenderer, replace_mermaid_blocks

from .html_cleanup import (
    collect_image_refs,
    expand_tabbed_content,
    extract_svgs,
    html_to_xhtml,
    restore_svgs_as_images,
    strip_site_chrome,
)
from .toc_builder import build_spine_order, build_toc

log = logging.getLogger("mkdocs.plugins.epub-generate")

_MIN_CONTENT_LENGTH = 200


class EpubGeneratePlugin(BasePlugin):
    config_scheme = (
        ("enabled", opt.Type(bool, default=False)),
        ("output", opt.Type(str, default="book.epub")),
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
        self._renderer = MermaidRenderer(self._cache_dir)
        self._chapter_queue = []  # [(src_path, title, cleaned_html), ...]
        self._all_images = set()
        self._extra_css = ""
        for css_path in self.config["stylesheets"]:
            p = self._config_dir / css_path
            if p.exists():
                self._extra_css += p.read_text() + "\n"
        log.info("[epub] Plugin enabled")

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
        # Skip pages with no real content
        text = re.sub(r"<[^>]+>", "", output)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < _MIN_CONTENT_LENGTH:
            log.info("[epub] Skipping empty page: %s", page.file.src_path)
            return output

        try:
            cleaned = self._prepare_epub_html(output)
            # Collect image references, resolve relative to page's dest dir
            raw_images = collect_image_refs(cleaned)
            page_dest_dir = Path(page.file.dest_path).parent
            for img in raw_images:
                if img.startswith(("http://", "https://", "//")):
                    continue
                # Resolve relative paths against page directory
                resolved = (page_dest_dir / img).as_posix()
                # Normalize ../ references
                resolved = posixpath.normpath(resolved)
                self._all_images.add(resolved)
            # Get page title
            title = page.title or page.file.src_path
            self._chapter_queue.append((page.file.src_path, title, cleaned))
        except Exception as e:
            log.warning("[epub] Failed processing: %s — %s",
                        page.file.src_path, str(e)[:120])

        return output  # web version unchanged

    def on_post_build(self, config, **kwargs):
        if not self.config["enabled"]:
            return
        if not self._chapter_queue:
            return
        t0 = time.monotonic()
        self._assemble_epub(config)
        elapsed = time.monotonic() - t0
        log.info("[epub] Done in %.1fs", elapsed)

    # ── HTML preprocessing ──

    def _prepare_epub_html(self, html):
        """Transform rendered HTML for EPUB, pre-XHTML step."""
        html = strip_site_chrome(html)
        html = replace_mermaid_blocks(html, self._cache_dir)
        html = expand_tabbed_content(html)
        return html

    # ── EPUB assembly ──

    def _assemble_epub(self, config):
        """Build the complete EPUB file."""
        book = epub.EpubBook()

        # Metadata
        book.set_identifier("aosp-internals-epub")
        book.set_title(config.get("site_name", "Book"))
        book.set_language("en")
        book.add_author("AOSP Internals Contributors")
        book.add_metadata("DC", "description",
                          config.get("site_description", ""))
        book.add_metadata("DC", "date",
                          datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        # Cover
        self._add_cover(book, config)

        # Stylesheet
        css_content = self._extra_css
        style = epub.EpubItem(
            uid="style",
            file_name="style/epub.css",
            media_type="text/css",
            content=css_content.encode("utf-8"),
        )
        book.add_item(style)

        # Build chapter map: src_path -> EpubHtml
        chapter_map = {}
        svg_file_names_added: set[str] = set()
        for src_path, title, content in self._chapter_queue:
            fname = src_path.replace(".md", ".xhtml")
            # Shield SVGs from the HTML→XHTML round-trip, then materialize
            # each SVG as a separate EPUB manifest item and reference it
            # from the chapter via <img>. Inline <svg> doesn't survive
            # ebooklib's HTML-based re-parsing during write_epub (case is
            # lost on viewBox, clipPath, etc.), and <img> is sized far
            # more predictably by EPUB readers.
            html_with_placeholders, svgs = extract_svgs(content)
            xhtml = html_to_xhtml(html_with_placeholders)
            xhtml, svg_files = restore_svgs_as_images(xhtml, svgs)
            for svg_filename, svg_bytes in svg_files:
                if svg_filename in svg_file_names_added:
                    continue
                svg_file_names_added.add(svg_filename)
                book.add_item(epub.EpubItem(
                    file_name=svg_filename,
                    media_type="image/svg+xml",
                    content=svg_bytes,
                ))
            # Rewrite internal links
            xhtml = self._rewrite_links(xhtml)

            ch = epub.EpubHtml(
                title=title,
                file_name=fname,
                lang="en",
            )
            ch.set_content(xhtml.encode("utf-8"))
            ch.add_item(style)
            book.add_item(ch)
            chapter_map[src_path] = ch

        # Images
        self._add_images(book, config)

        # ToC and spine from nav config
        nav_config = config.get("nav", [])
        book.toc = build_toc(nav_config, chapter_map)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Spine: reading order from nav
        spine_order = build_spine_order(nav_config)
        spine = ["nav"]
        for src in spine_order:
            if src in chapter_map:
                spine.append(chapter_map[src])
        book.spine = spine

        # Write
        output_path = Path(config["site_dir"]) / self.config["output"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(output_path), book)

        size_mb = output_path.stat().st_size / 1024 / 1024
        log.info("[epub] Written: %s (%.1f MB)", output_path.name, size_mb)
        if size_mb > 100:
            log.warning("[epub] EPUB exceeds 100MB — consider SVG optimization")

    def _add_cover(self, book, config):
        """Render cover SVG to PNG and set as EPUB cover."""
        cover_source = self.config.get("cover", "")
        if not cover_source:
            return

        cover_file = self._config_dir / cover_source
        if not cover_file.exists():
            log.warning("[epub] Cover file not found: %s", cover_source)
            return

        try:
            from playwright.sync_api import sync_playwright

            if cover_source.endswith(".svg"):
                svg_data = cover_file.read_text()
                html = f"""\
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
html, body {{ margin: 0; padding: 0; width: 1600px; height: 2560px; overflow: hidden; }}
body {{ display: flex; align-items: center; justify-content: center; background: #fff; }}
svg {{ max-width: 1600px; max-height: 2560px; width: auto; height: auto; }}
</style>
</head><body>{svg_data}</body></html>"""
            else:
                return  # Only SVG covers supported for EPUB

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True, args=["--no-sandbox"])
                page = browser.new_page(
                    viewport={"width": 1600, "height": 2560})
                page.set_content(html, wait_until="load",
                                 timeout=self.config["timeout"])
                png_bytes = page.screenshot(type="png", full_page=False)
                page.close()
                browser.close()

            book.set_cover("cover.png", png_bytes)
            log.info("[epub] Cover rendered from %s", cover_source)

        except Exception as e:
            log.warning("[epub] Cover rendering failed: %s", str(e)[:120])

    def _add_images(self, book, config):
        """Add referenced images to the EPUB."""
        site_dir = Path(config["site_dir"])
        for img_path in self._all_images:
            full_path = site_dir / img_path
            if not full_path.exists():
                log.warning("[epub] Image not found: %s", img_path)
                continue
            try:
                media_type = mimetypes.guess_type(str(full_path))[0]
                if not media_type:
                    media_type = "application/octet-stream"
                img_item = epub.EpubItem(
                    file_name=img_path,
                    media_type=media_type,
                    content=full_path.read_bytes(),
                )
                book.add_item(img_item)
            except Exception as e:
                log.warning("[epub] Failed to add image %s: %s",
                            img_path, str(e)[:80])

    def _rewrite_links(self, html):
        """Rewrite internal .html links to .xhtml for EPUB."""

        def _rewrite(m):
            href = m.group(1)
            # Skip external links
            if href.startswith(("http://", "https://", "//")):
                return m.group(0)
            # Strip /index.html or .html suffix, add .xhtml
            href = re.sub(r"(?:/index)?\.html", ".xhtml", href)
            return f'href="{href}"'

        html = re.sub(r'href="([^"]*\.html[^"]*)"', _rewrite, html)
        return html
