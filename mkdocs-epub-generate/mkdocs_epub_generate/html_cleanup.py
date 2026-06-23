"""HTML cleanup utilities for EPUB generation."""

import hashlib
import logging
import re
from pathlib import Path

from lxml import etree, html

log = logging.getLogger("mkdocs.plugins.epub-generate.html_cleanup")


def strip_site_chrome(html_str: str) -> str:
    """Extract article content from Material theme HTML, removing all site chrome.

    Instead of trying to strip individual elements (header, sidebar, footer...),
    we extract the actual content from <article class="md-content__inner md-typeset">
    which is the only part that matters for EPUB.
    """
    # Try to extract just the article content
    m = re.search(
        r'<article[^>]*class="[^"]*md-typeset[^"]*"[^>]*>(.*)</article>',
        html_str,
        re.DOTALL,
    )
    if m:
        content = m.group(1)
    else:
        # Fallback: strip known chrome elements
        content = html_str
        patterns = [
            r"<header[^>]*>.*?</header>",
            r"<footer[^>]*>.*?</footer>",
            r"<nav[^>]*>.*?</nav>",
            r'<div[^>]*class="[^"]*md-sidebar[^"]*"[^>]*>.*?</div>',
            r'<div[^>]*class="[^"]*md-tabs[^"]*"[^>]*>.*?</div>',
            r'<div[^>]*class="[^"]*md-header[^"]*"[^>]*>.*?</div>',
        ]
        for pattern in patterns:
            content = re.sub(pattern, "", content, flags=re.DOTALL)

    # Remove remaining Material-specific elements
    content = re.sub(r'<input[^>]*/?\s*>', "", content)
    content = re.sub(r'<label[^>]*class="[^"]*md-[^"]*"[^>]*>.*?</label>', "", content, flags=re.DOTALL)
    content = re.sub(r'<label[^>]*for="__[^"]*"[^>]*/?\s*>', "", content)
    content = re.sub(r'<a[^>]*class="[^"]*md-skip[^"]*"[^>]*>.*?</a>', "", content, flags=re.DOTALL)
    content = re.sub(r'<a[^>]*class="[^"]*headerlink[^"]*"[^>]*>.*?</a>', "", content, flags=re.DOTALL)
    content = re.sub(r'<button[^>]*class="[^"]*md-clipboard[^"]*"[^>]*>.*?</button>', "", content, flags=re.DOTALL)
    content = re.sub(r'<div[^>]*id="mermaid-zoom-overlay"[^>]*>.*?</div>', "", content, flags=re.DOTALL)
    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)

    # Expand <details> elements
    content = re.sub(r"<details(?!\s+open)", "<details open", content)

    return content


def expand_tabbed_content(html_str: str) -> str:
    """Expand pymdownx.tabbed content: show all panels sequentially."""
    html_str = re.sub(
        r'<input[^>]*name="__tabbed[^"]*"[^>]*/?>',
        "",
        html_str,
    )
    html_str = re.sub(
        r'<label[^>]*for="__tabbed[^"]*"[^>]*>(.*?)</label>',
        r"<h4>\1</h4>",
        html_str,
        flags=re.DOTALL,
    )
    html_str = re.sub(
        r'<div[^>]*class="[^"]*tabbed-set[^"]*"[^>]*>',
        "<div>",
        html_str,
    )
    return html_str


def html_to_xhtml(html_str: str) -> str:
    """Convert HTML5 to valid XHTML for EPUB3.

    Uses ``html.fragments_fromstring`` instead of ``html.fromstring`` so that
    HTML comments appearing before the first element (e.g. ``<!--__SVG_0__-->``
    placeholders emitted by ``extract_svgs``) are not silently discarded by
    lxml's fragment parser.  A single-element fragment is returned as-is
    (no extra ``<div>`` wrapper); multi-node fragments are wrapped in ``<div>``.
    """
    try:
        frags = html.fragments_fromstring(html_str)
        if len(frags) == 1 and not isinstance(frags[0], str):
            # Single-element fragment — serialize directly, no wrapper needed.
            return etree.tostring(frags[0], encoding="unicode", method="xml")
        # Multiple nodes (or a leading text node) — collect into a <div>.
        wrapper = etree.Element("div")
        prev = None
        for frag in frags:
            if isinstance(frag, str):
                if prev is None:
                    wrapper.text = (wrapper.text or "") + frag
                else:
                    prev.tail = (prev.tail or "") + frag
            else:
                wrapper.append(frag)
                prev = frag
        return etree.tostring(wrapper, encoding="unicode", method="xml")
    except Exception:
        html_str = re.sub(r"<br\s*/?>", "<br/>", html_str)
        html_str = re.sub(r"<img([^>]*?)(?<!/)>", r"<img\1/>", html_str)
        html_str = re.sub(r"<hr\s*/?>", "<hr/>", html_str)
        return html_str


_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_EPUB_MAX_WIDTH_PX = 550
# Conservative single-page height cap that fits common readers (Kindle,
# Kobo, compact phone viewers) without CSS-assist. Large-screen readers
# use the epub.css max-height: 85vh rule for responsive scaling on top.
_EPUB_MAX_HEIGHT_PX = 600

_XLINK_DECL_RE = re.compile(r'\bxmlns:xlink\s*=')
_XLINK_USE_RE = re.compile(r'\bxlink:[A-Za-z]')
_SVG_OPEN_RE = re.compile(r"<svg\b", re.IGNORECASE)


def _inject_xlink_namespace_if_needed(svg_text: str) -> str:
    """Add xmlns:xlink to the root <svg> tag if xlink: is used without it.

    lxml's XML parser will raise on an undeclared xlink: prefix, and even
    when it doesn't, a missing binding causes the namespace to be
    re-serialized under a synthetic prefix like ns0:. Inject the standard
    binding before parsing.
    """
    if not _XLINK_USE_RE.search(svg_text):
        return svg_text
    if _XLINK_DECL_RE.search(svg_text):
        return svg_text
    return _SVG_OPEN_RE.sub(f'<svg xmlns:xlink="{_XLINK_NS}"', svg_text, count=1)


def normalize_svg_xhtml(svg_text: str, unique_prefix: str = "") -> str:
    """Parse one SVG string, clean it up for EPUB, and re-serialize.

    - Replaces <foreignObject> with a plain SVG <text> carrying the HTML
      label's text content (strict EPUB readers don't render
      foreignObject consistently; Mermaid uses it for ~74% of labels, so
      blindly stripping it erases most node/edge labels).
    - Sets explicit width/height from viewBox, scaled to a ~550px viewport.
    - Removes the root element's style= attribute; leaves child <style> alone.
    - Injects xmlns:xlink when needed.
    - Rewrites every id declared in this SVG (root and descendants) plus
      every "#id" reference with unique_prefix, so ids are globally unique
      across the EPUB. Mermaid emits many derived ids that are not scoped
      by the root id (e.g. "flowchart-D-5", "solidBottomArrowHead"), so
      prefixing only the root would allow cross-diagram id collisions
      that strict EPUB readers reject as invalid XHTML.
    - On parse failure, returns a broken-diagram placeholder.
    """
    try:
        svg_text = _inject_xlink_namespace_if_needed(svg_text)
        root = etree.fromstring(svg_text.encode("utf-8"))

        # Replace each foreignObject with an SVG <text> element containing
        # its text content, positioned at the center of the fo's bounding box.
        for fo in list(root.findall(f".//{{{_SVG_NS}}}foreignObject")):
            parent = fo.getparent()
            if parent is None:
                continue
            label = re.sub(r"\s+", " ", "".join(fo.itertext())).strip()
            idx = parent.index(fo)
            if label:
                try:
                    x = float(fo.get("x", "0"))
                    y = float(fo.get("y", "0"))
                    w = float(fo.get("width", "0"))
                    h = float(fo.get("height", "0"))
                except (TypeError, ValueError):
                    x = y = w = h = 0.0
                text_elem = etree.Element(f"{{{_SVG_NS}}}text")
                text_elem.set("x", str(x + w / 2))
                text_elem.set("y", str(y + h / 2))
                text_elem.set("text-anchor", "middle")
                text_elem.set("dominant-baseline", "central")
                text_elem.text = label
                parent.insert(idx, text_elem)
            parent.remove(fo)

        # Size from viewBox. Cap both dimensions (not just width) so tall
        # narrow diagrams don't overflow EPUB pages — the reader would
        # otherwise render them at intrinsic height and visibly clip.
        # A single uniform scale preserves aspect ratio.
        vb = root.get("viewBox")
        if vb:
            parts = vb.split()
            if len(parts) == 4:
                try:
                    vb_w = float(parts[2])
                    vb_h = float(parts[3])
                    if vb_w > 0 and vb_h > 0:
                        scale = min(
                            1.0,
                            _EPUB_MAX_WIDTH_PX / vb_w,
                            _EPUB_MAX_HEIGHT_PX / vb_h,
                        )
                        root.set("width", str(int(vb_w * scale)))
                        root.set("height", str(int(vb_h * scale)))
                except (ValueError, ZeroDivisionError):
                    pass

        # Strip root style
        if "style" in root.attrib:
            del root.attrib["style"]

        # Prefix every id declared in this SVG (root + descendants) with
        # unique_prefix, then rewrite every "#id" reference to match.
        # Mermaid emits plenty of derived ids that don't contain the root
        # mmdN as a token — "solidBottomArrowHead", "flowchart-D-5",
        # "subGraph4", "L_E_F_0" — so prefixing only the root would leave
        # those to collide across diagrams in the same chapter and break
        # strict EPUB readers on duplicate-id grounds.
        # Mermaid occasionally emits the same id on multiple elements within
        # one SVG (e.g. "node-undefined" is used as both id and class on
        # every fallback-classed node). Those were already malformed per
        # XHTML, just masked by the narrower id scope. Deduplicate here
        # by suffixing collisions with "_2", "_3", … so the renamed ids
        # are guaranteed unique inside each SVG. References to the original
        # id map to the first occurrence (which is what <foo id="X"> had
        # effectively selected when multiple shared the same id).
        old_to_new: dict[str, str] = {}
        used_new_ids: set[str] = set()
        for elem in root.iter():
            old_id = elem.get("id")
            if not old_id:
                continue
            base = f"{unique_prefix}_{old_id}" if unique_prefix else old_id
            new_id = base
            suffix = 2
            while new_id in used_new_ids:
                new_id = f"{base}_{suffix}"
                suffix += 1
            used_new_ids.add(new_id)
            elem.set("id", new_id)
            old_to_new.setdefault(old_id, new_id)

        if old_to_new:
            # Sort longest-first so alternation matches the fullest id
            # (e.g. "flowchart-D-5" before "flowchart-D") — regex
            # alternation is first-match, not longest-match.
            alternation = "|".join(
                re.escape(i) for i in sorted(old_to_new, key=len, reverse=True)
            )
            # Anchor references on "#" and a trailing non-alnum token
            # boundary so we only rewrite real id references and never
            # touch label text or hex color literals like "#4CAF50".
            ref_re = re.compile(rf"#({alternation})(?![A-Za-z0-9])")

            def _sub(m: re.Match) -> str:
                return "#" + old_to_new[m.group(1)]

            for elem in root.iter():
                for attr_name, attr_val in list(elem.attrib.items()):
                    if attr_name == "id" or "#" not in attr_val:
                        continue
                    new_val = ref_re.sub(_sub, attr_val)
                    if new_val != attr_val:
                        elem.set(attr_name, new_val)
                if elem.text and "#" in elem.text:
                    new_text = ref_re.sub(_sub, elem.text)
                    if new_text != elem.text:
                        elem.text = new_text
                if elem.tail and "#" in elem.tail:
                    new_tail = ref_re.sub(_sub, elem.tail)
                    if new_tail != elem.tail:
                        elem.tail = new_tail

        return etree.tostring(root, encoding="unicode")
    except etree.XMLSyntaxError as exc:
        log.warning(
            "[epub] SVG parse failed (%s); emitting broken-diagram placeholder",
            str(exc)[:100],
        )
        return '<div class="mermaid-broken">[diagram unavailable]</div>'


_SVG_PATTERN = re.compile(r"<svg\b[^>]*>.*?</svg>", re.DOTALL | re.IGNORECASE)


def extract_svgs(html_str: str) -> tuple[str, list[str]]:
    """Replace each top-level <svg>…</svg> with a numbered HTML comment.

    Returns (html_with_placeholders, list_of_raw_svg_strings_in_order).
    HTML comments pass through lxml's HTML parser and XML serializer
    unchanged, so they are a safe anchor for `restore_svgs`.
    """
    svgs: list[str] = []

    def _sub(m: re.Match) -> str:
        idx = len(svgs)
        svgs.append(m.group(0))
        return f"<!--__SVG_{idx}__-->"

    new_html = _SVG_PATTERN.sub(_sub, html_str)
    return new_html, svgs


_PLACEHOLDER_PATTERN = re.compile(r"<!--__SVG_(\d+)__-->")


def chapter_slug_for(src_path: str) -> str:
    """Derive a chapter slug safe for use as a CSS id prefix.

    Prepends 'ch' to the filename stem so slugs that start with a digit
    (e.g. '07-bionic-and-linker') don't produce CSS identifiers beginning
    with a digit — those are invalid per CSS3 and strict EPUB readers drop
    the enclosing rule, which would leave scoped Mermaid styles inert.
    """
    return f"ch{Path(src_path).stem}"


_SVG_XML_PROLOG = '<?xml version="1.0" encoding="UTF-8"?>\n'


def _split_root_dimensions(svg_text: str) -> tuple[str, int, int]:
    """Strip width/height from the root <svg> and return (svg, w, h).

    Embedded width/height attributes give the SVG a fixed intrinsic pixel
    size. Many EPUB readers (Apple Books, several Android readers) honor
    that intrinsic size by rasterizing the SVG at exactly those pixel
    counts and then upscaling the bitmap to the viewport when the user
    opens an image in zoom view — which produces a visibly blurry
    enlargement.

    Removing width/height from the SVG file leaves it as pure vector with
    only a viewBox: the reader is free to render at the zoomed resolution
    on demand. Inline display size is then driven by width/height set on
    the wrapping <img> tag, which respects the epub.css max-width:100%
    constraint for small-screen readers.

    Returns (stripped_svg, 0, 0) when width/height are absent or the SVG
    fails to parse, signalling the caller to omit dimensions on the <img>.
    """
    try:
        root = etree.fromstring(svg_text.encode("utf-8"))
    except etree.XMLSyntaxError:
        return svg_text, 0, 0

    def _to_int(val: str | None) -> int:
        if not val:
            return 0
        try:
            return int(float(val))
        except ValueError:
            return 0

    w = _to_int(root.get("width"))
    h = _to_int(root.get("height"))
    if "width" in root.attrib:
        del root.attrib["width"]
    if "height" in root.attrib:
        del root.attrib["height"]
    return etree.tostring(root, encoding="unicode"), w, h


def restore_svgs_as_images(
    xhtml_str: str,
    svg_list: list[str],
    dir_prefix: str = "mermaid",
) -> tuple[str, list[tuple[str, bytes]]]:
    """Replace each <!--__SVG_N__--> placeholder with an <img> element
    whose src points to a separate SVG file in the EPUB manifest.

    Returns (new_xhtml, list_of_(filename, svg_bytes)). The caller is
    responsible for adding each svg_bytes to the EPUB as an item with
    media type image/svg+xml.

    Filenames are derived from a hash of the normalized SVG content, so
    identical diagrams deduplicate to a single manifest entry referenced
    from every place they appear.

    Using <img> instead of inline <svg> sidesteps two classes of problem:
    - ebooklib re-parses chapter XHTML through an HTML parser during
      write_epub, which lowercases case-sensitive SVG attributes
      (viewBox, clipPath, linearGradient…). External SVG file bytes are
      written opaquely, so their case is preserved.
    - <img> respects CSS max-width/max-height universally across EPUB
      readers, so tall diagrams don't clip on small-screen readers.

    Pixel dimensions computed by normalize_svg_xhtml are stripped from
    the saved SVG file and copied to the <img> tag instead, so the SVG
    stays purely vector for crisp rendering when the user opens the
    diagram in a reader's zoom view.
    """
    svg_files: list[tuple[str, bytes]] = []
    seen_hashes: set[str] = set()

    def _sub(m: re.Match) -> str:
        idx = int(m.group(1))
        if idx >= len(svg_list):
            log.warning(
                "[epub] SVG placeholder __SVG_%d__ has no matching entry",
                idx,
            )
            return m.group(0)
        # Each SVG file is its own document, so cross-SVG id scoping is
        # structurally impossible. normalize_svg_xhtml still deduplicates
        # ids that Mermaid emits multiple times within a single SVG.
        normalized = normalize_svg_xhtml(svg_list[idx])
        stripped, width, height = _split_root_dimensions(normalized)
        svg_bytes = (_SVG_XML_PROLOG + stripped).encode("utf-8")
        svg_hash = hashlib.sha256(svg_bytes).hexdigest()[:16]
        filename = f"{dir_prefix}/{svg_hash}.svg"
        if svg_hash not in seen_hashes:
            seen_hashes.add(svg_hash)
            svg_files.append((filename, svg_bytes))
        if width > 0 and height > 0:
            return (
                f'<img src="{filename}" width="{width}" height="{height}" '
                'alt="Diagram"/>'
            )
        return f'<img src="{filename}" alt="Diagram"/>'

    new_xhtml = _PLACEHOLDER_PATTERN.sub(_sub, xhtml_str)
    return new_xhtml, svg_files


def collect_image_refs(html_str: str) -> list[str]:
    """Collect unique non-Mermaid image src paths from HTML."""
    refs = re.findall(r'<img[^>]*\bsrc="([^"]+)"', html_str)
    seen = set()
    unique = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique.append(ref)
    return unique
