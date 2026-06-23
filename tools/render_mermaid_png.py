"""Convert cached Mermaid SVGs to PNG for visual review (and refresh the SVG cache).

PNGs (unlike the SVGs the build pipeline uses) can be opened by image-viewing
tools and the multimodal Read tool, which lets a reviewer eyeball each diagram
for layout problems (text overflow, overlapping nodes, unreadable arrows) and
factual accuracy (does the diagram match the prose around it).

The pdf-generate / epub-generate plugins produce ``.mermaid-cache/<sha16>.svg``
for every Mermaid block. This script reuses those SVGs — it does not re-run
Mermaid for already-cached diagrams — and only loads them in headless Chromium
long enough to take a screenshot.

When a mermaid block has been edited, the new content has a new hash and there
is no cached SVG yet. This script renders any missing SVGs first via the
shared ``mkdocs_mermaid_renderer`` (the same Playwright + Mermaid pipeline used
by the pdf/epub plugins). That way ``.mermaid-cache/`` always reflects the
current markdown, and a subsequent ``serve.sh pdf`` or ``serve.sh epub`` build
gets cache hits for everything.

Usage (run inside the book-serve Docker image, which already has Playwright):

    docker run --rm -v "$PWD":/book -w /book book-serve \\
        python3 tools/render_mermaid_png.py 22-activity-and-window.md

    # All chapters:
    docker run --rm -v "$PWD":/book -w /book book-serve \\
        python3 tools/render_mermaid_png.py --all

Output: ``.mermaid-png/<chapter-slug>/NN-<sha16>.png``.
``NN`` is the 1-based occurrence index of the mermaid block within the chapter,
so ``22-activity-and-window/03-<hash>.png`` is the third diagram in chapter 22.
The hash matches the one used by the SVG cache, so a diagram appearing in two
chapters is rendered only once.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

MERMAID_BLOCK_RE = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL)

# Pages just need to host one SVG and let Chromium screenshot the bounding box.
# No Mermaid library, no JS needed beyond what styles the SVG.
PAGE_HTML = """\
<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 24px; background: white; font-family: Roboto, sans-serif; }
  #diagram { display: inline-block; }
  /* Cancel the build-pipeline rule that constrains SVGs to the page width. */
  #diagram svg { max-width: none !important; max-height: none !important; }
</style>
</head><body>
<div id="diagram"></div>
</body></html>
"""

# The multimodal Read tool rejects images with any side > 2000 px in
# many-image requests. Cap below that with a margin.
MAX_SIDE_PX = 1800


def _hash16(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()[:16]


def _extract_blocks(md_path: Path) -> list[tuple[int, str]]:
    """Return ``[(index, code), ...]`` for each mermaid block, 1-based."""
    blocks = MERMAID_BLOCK_RE.findall(md_path.read_text())
    return [(i + 1, code.strip()) for i, code in enumerate(blocks)]


def _scaled_svg(svg_text: str) -> str:
    """Force the root <svg> to MAX_SIDE_PX on its longest side.

    Mermaid emits SVGs with a viewBox and width/height set to the natural
    pixel size; some are 3000+ px wide. Without scaling, screenshots would
    overflow the Read tool's image limit.
    """
    m = re.search(r'<svg\b[^>]*viewBox="([^"]+)"', svg_text)
    if not m:
        return svg_text
    parts = re.split(r"[\s,]+", m.group(1).strip())
    if len(parts) != 4:
        return svg_text
    try:
        _, _, w, h = map(float, parts)
    except ValueError:
        return svg_text
    if w <= 0 or h <= 0:
        return svg_text
    scale = min(1.0, MAX_SIDE_PX / max(w, h))
    out_w = round(w * scale)
    out_h = round(h * scale)
    # Strip any existing width/height/style and re-set them.
    svg_text = re.sub(r'\s(?:width|height|style)="[^"]*"', "", svg_text, count=3)
    svg_text = svg_text.replace(
        "<svg",
        f'<svg width="{out_w}" height="{out_h}" style="width:{out_w}px;height:{out_h}px"',
        1,
    )
    return svg_text


def render_chapter(
    md_path: Path,
    out_root: Path,
    cache_dir: Path,
    page,
) -> tuple[int, int, list[str]]:
    """Convert every mermaid block's cached SVG to PNG. Returns (rendered, skipped, errors)."""
    blocks = _extract_blocks(md_path)
    if not blocks:
        return 0, 0, []

    chapter_slug = md_path.stem
    out_dir = out_root / chapter_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    rendered = skipped = 0
    errors: list[str] = []

    for idx, code in blocks:
        h = _hash16(code)
        png_path = out_dir / f"{idx:02d}-{h}.png"
        if png_path.exists():
            skipped += 1
            continue
        svg_path = cache_dir / f"{h}.svg"
        if not svg_path.exists():
            # Should not happen — _refresh_svg_cache populated everything before
            # this loop. Treat as an error so the user notices.
            errors.append(
                f"{md_path.name} block #{idx} ({h}): SVG missing from cache "
                "after refresh — Mermaid likely failed to render this block"
            )
            continue
        try:
            svg = _scaled_svg(svg_path.read_text())
            page.evaluate(
                "svg => { document.getElementById('diagram').innerHTML = svg; }",
                svg,
            )
            page.wait_for_selector("#diagram svg", timeout=10000)
            elem = page.query_selector("#diagram")
            elem.screenshot(path=str(png_path), omit_background=False)
            rendered += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{md_path.name} block #{idx} ({h}): {e!s:.200}")

    return rendered, skipped, errors


def _refresh_svg_cache(targets: list[Path], cache_dir: Path) -> int:
    """Render any mermaid block whose SVG isn't in cache.

    Uses the same `mkdocs_mermaid_renderer` the pdf/epub plugins use, so the
    cache it leaves behind serves both PNG conversion here and a subsequent
    ``serve.sh pdf|epub`` build with no extra work.

    Returns the number of SVGs newly rendered. Idempotent — already-cached
    blocks are skipped.
    """
    from mkdocs_mermaid_renderer import MermaidRenderer

    cache_dir.mkdir(exist_ok=True)
    renderer = MermaidRenderer(cache_dir)
    for md in targets:
        for _, code in _extract_blocks(md):
            renderer.queue(code)
    pending = len(renderer._queue)  # noqa: SLF001 — public field is missing
    if pending:
        print(f"Rendering {pending} new SVG(s) into {cache_dir}/ ...")
        renderer.render_batch()
    return pending


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "chapters",
        nargs="*",
        help="Chapter markdown files (e.g. 22-activity-and-window.md). Empty + --all renders everything.",
    )
    p.add_argument("--all", action="store_true", help="Render every NN-*.md and A-/B-*.md chapter")
    p.add_argument("--out", default=".mermaid-png", help="Output root directory")
    p.add_argument("--cache", default=".mermaid-cache", help="SVG cache directory (input)")
    p.add_argument("--force", action="store_true", help="Re-render even if PNG already cached")
    args = p.parse_args()

    if not args.chapters and not args.all:
        p.error("specify one or more chapters or --all")

    book_root = Path.cwd()
    out_root = book_root / args.out
    cache_dir = book_root / args.cache

    if args.all:
        targets = sorted(book_root.glob("[0-9][0-9]-*.md"))
        targets += sorted(book_root.glob("[A-Z]-*.md"))
    else:
        targets = []
        for name in args.chapters:
            target = book_root / name
            if not target.exists():
                print(f"error: {target} does not exist", file=sys.stderr)
                return 2
            targets.append(target)

    if args.force:
        for t in targets:
            slug_dir = out_root / t.stem
            if slug_dir.exists():
                for f in slug_dir.iterdir():
                    f.unlink()

    # Make sure every mermaid block has an SVG in the shared cache before we
    # screenshot. This also primes ``.mermaid-cache/`` for the next pdf/epub
    # build, so editing a diagram never leaves stale SVGs lying around.
    _refresh_svg_cache(targets, cache_dir)

    from playwright.sync_api import sync_playwright

    total_rendered = total_skipped = 0
    all_errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_content(PAGE_HTML)

        for md in targets:
            r, s, e = render_chapter(md, out_root, cache_dir, page)
            total_rendered += r
            total_skipped += s
            all_errors.extend(e)
            if r or s or e:
                print(f"{md.name}: rendered={r} skipped={s} errors={len(e)}")

        browser.close()

    print(f"\nTotal rendered={total_rendered} skipped={total_skipped} errors={len(all_errors)}")
    for err in all_errors:
        print(f"  {err}")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
