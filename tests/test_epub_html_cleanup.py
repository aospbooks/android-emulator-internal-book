"""Tests for EPUB HTML cleanup functions."""

from mkdocs_epub_generate.html_cleanup import (
    strip_site_chrome,
    expand_tabbed_content,
    html_to_xhtml,
    collect_image_refs,
    extract_svgs,
    normalize_svg_xhtml,
    restore_svgs_as_images,
    chapter_slug_for,
)


class TestStripSiteChrome:
    def test_removes_header(self):
        html = '<div>content</div><header class="md-header">nav</header>'
        assert "md-header" not in strip_site_chrome(html)

    def test_removes_footer(self):
        html = '<div>content</div><footer class="md-footer">foot</footer>'
        assert "md-footer" not in strip_site_chrome(html)

    def test_removes_sidebar(self):
        html = '<div class="md-sidebar">sidebar</div><div>content</div>'
        assert "md-sidebar" not in strip_site_chrome(html)

    def test_removes_scripts(self):
        html = '<div>content</div><script>alert(1)</script>'
        assert "<script" not in strip_site_chrome(html)

    def test_preserves_content(self):
        html = '<div class="md-content"><p>Hello world</p></div>'
        assert "Hello world" in strip_site_chrome(html)

    def test_opens_details(self):
        html = '<details><summary>Info</summary><p>Hidden</p></details>'
        result = strip_site_chrome(html)
        assert "<details open" in result



class TestExpandTabbedContent:
    def test_expands_tabs(self):
        html = (
            '<div class="tabbed-set" data-tabs="1">'
            '<input type="radio" name="__tabbed_1" id="__tabbed_1_1" checked>'
            '<label for="__tabbed_1_1">Tab A</label>'
            '<div class="tabbed-content">'
            '<div class="tabbed-block"><p>Content A</p></div>'
            '</div>'
            '<input type="radio" name="__tabbed_1" id="__tabbed_1_2">'
            '<label for="__tabbed_1_2">Tab B</label>'
            '<div class="tabbed-content">'
            '<div class="tabbed-block"><p>Content B</p></div>'
            '</div>'
            '</div>'
        )
        result = expand_tabbed_content(html)
        assert "Content A" in result
        assert "Content B" in result
        assert '<input type="radio"' not in result


class TestHtmlToXhtml:
    def test_self_closing_br(self):
        result = html_to_xhtml("<p>line1<br>line2</p>")
        assert "<br/>" in result or "<br />" in result

    def test_self_closing_img(self):
        result = html_to_xhtml('<p><img src="test.png"></p>')
        assert "/>" in result

    def test_preserves_content(self):
        result = html_to_xhtml("<p>Hello &amp; world</p>")
        assert "Hello" in result
        assert "world" in result


class TestCollectImageRefs:
    def test_finds_img_tags(self):
        html = '<img src="images/fig1.png"><img src="images/fig2.jpg">'
        refs = collect_image_refs(html)
        assert "images/fig1.png" in refs
        assert "images/fig2.jpg" in refs

    def test_skips_mermaid_svgs(self):
        html = '<div class="mermaid-svg"><svg>...</svg></div><img src="real.png">'
        refs = collect_image_refs(html)
        assert "real.png" in refs
        assert len(refs) == 1

    def test_deduplicates(self):
        html = '<img src="a.png"><img src="a.png">'
        refs = collect_image_refs(html)
        assert len(refs) == 1


class TestExtractSvgs:
    def test_single_svg_replaced_with_placeholder(self):
        html = '<p>before</p><svg viewBox="0 0 10 10"><rect/></svg><p>after</p>'
        new_html, svgs = extract_svgs(html)
        assert "<svg" not in new_html
        assert "<!--__SVG_0__-->" in new_html
        assert svgs == ['<svg viewBox="0 0 10 10"><rect/></svg>']

    def test_multiple_svgs_numbered_in_order(self):
        html = '<svg id="a"><rect/></svg>middle<svg id="b"><circle/></svg>'
        new_html, svgs = extract_svgs(html)
        assert new_html == '<!--__SVG_0__-->middle<!--__SVG_1__-->'
        assert svgs[0] == '<svg id="a"><rect/></svg>'
        assert svgs[1] == '<svg id="b"><circle/></svg>'

    def test_no_svg_returns_empty_list(self):
        html = '<p>no diagrams here</p>'
        new_html, svgs = extract_svgs(html)
        assert new_html == html
        assert svgs == []

    def test_preserves_mermaid_svg_wrapper(self):
        # The <div class="mermaid-svg"> wrapper from replace_mermaid_blocks
        # stays put; only the inner <svg> is extracted. Mermaid never emits
        # self-closing <svg/>, so the test uses an explicit closing tag.
        html = '<div class="mermaid-svg"><svg viewBox="0 0 5 5"><rect/></svg></div>'
        new_html, svgs = extract_svgs(html)
        assert new_html == '<div class="mermaid-svg"><!--__SVG_0__--></div>'
        assert svgs == ['<svg viewBox="0 0 5 5"><rect/></svg>']

    def test_case_insensitive_svg_tags(self):
        # Defensive: handle upper/mixed case in case some pipeline stage
        # ever lowercases only partially.
        html = '<SVG viewBox="0 0 1 1"><rect/></SVG>'
        new_html, svgs = extract_svgs(html)
        assert "<!--__SVG_0__-->" in new_html
        assert len(svgs) == 1

    def test_does_not_match_across_unrelated_svgs(self):
        # Non-greedy matching must stop at the first </svg>, not span two.
        html = '<svg>a</svg> junk <svg>b</svg>'
        _, svgs = extract_svgs(html)
        assert svgs == ['<svg>a</svg>', '<svg>b</svg>']


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


class TestNormalizeSvgStructural:
    def test_preserves_viewBox_case(self):
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 100 50"><rect/></svg>'
        out = normalize_svg_xhtml(svg, "c01_0")
        assert 'viewBox="0 0 100 50"' in out
        assert "viewbox=" not in out

    def test_preserves_clipPath_and_linearGradient(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 10 10">'
            '<defs><clipPath id="clip0"><rect/></clipPath>'
            '<linearGradient id="g0"><stop/></linearGradient></defs>'
            '<rect clip-path="url(#clip0)" fill="url(#g0)"/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        assert "<clipPath" in out
        assert "<linearGradient" in out
        assert "<clippath" not in out
        assert "<lineargradient" not in out

    def test_foreignObject_converted_to_text_preserves_label(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 10 10">'
            '<foreignObject x="0" y="0" width="4" height="2">'
            '<div xmlns="http://www.w3.org/1999/xhtml">Label</div>'
            '</foreignObject>'
            '<rect/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        # The foreignObject tag is gone but its text content survives in
        # an SVG <text> element — this is what gives EPUB readers a
        # non-empty diagram label.
        assert "foreignObject" not in out
        assert "Label" in out
        assert "<text" in out
        assert "<rect" in out

    def test_foreignObject_text_centered_on_bounding_box(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 100 100">'
            '<foreignObject x="10" y="20" width="40" height="10">'
            '<div xmlns="http://www.w3.org/1999/xhtml">X</div>'
            '</foreignObject></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        from lxml import etree as _e
        root = _e.fromstring(out)
        texts = root.findall(f".//{{{SVG_NS}}}text")
        assert len(texts) == 1
        t = texts[0]
        # Center: x = 10 + 40/2 = 30, y = 20 + 10/2 = 25
        assert float(t.get("x")) == 30.0
        assert float(t.get("y")) == 25.0
        assert t.get("text-anchor") == "middle"
        assert t.get("dominant-baseline") == "central"

    def test_empty_foreignObject_is_removed_with_no_replacement(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 10 10">'
            '<foreignObject x="0" y="0" width="1" height="1"></foreignObject>'
            '<rect/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        assert "foreignObject" not in out
        from lxml import etree as _e
        root = _e.fromstring(out)
        # No text element inserted because the fo had no label content.
        assert root.findall(f".//{{{SVG_NS}}}text") == []
        assert root.findall(f".//{{{SVG_NS}}}rect")  # rect still present

    def test_foreignObject_with_nested_spans_combines_text(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 10 10">'
            '<foreignObject x="0" y="0" width="4" height="2">'
            '<div xmlns="http://www.w3.org/1999/xhtml">'
            '<span><span>Class</span>Name</span>'
            '</div></foreignObject></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        # Whitespace-collapsed concatenation preserves the visual label.
        assert "ClassName" in out

    def test_sets_pixel_dimensions_from_viewBox(self):
        # viewBox 0 0 1100 550 → scaled to fit 550-wide viewport → width=550 height=275
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 1100 550"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        assert 'width="550"' in out
        assert 'height="275"' in out

    def test_small_svg_keeps_natural_size(self):
        # viewBox smaller than 550 wide → scale 1 → width=100 height=50
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 100 50"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        assert 'width="100"' in out
        assert 'height="50"' in out

    def test_tall_svg_scaled_down_to_fit_max_height(self):
        # A tall narrow diagram (200 wide × 4000 tall) fits the 550-wide
        # viewport at natural width, but its height would overflow the
        # EPUB page. Must scale uniformly so height stays within the 600
        # pixel cap (conservative for readers without vh support),
        # preserving aspect ratio.
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 200 4000"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        # scale = min(1.0, 550/200, 600/4000) = min(1.0, 2.75, 0.15) = 0.15
        # → width=30, height=600
        assert 'width="30"' in out
        assert 'height="600"' in out

    def test_strips_root_style_attribute(self):
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 10 10" style="max-width: 555px;"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        assert "max-width" not in out

    def test_preserves_child_style_element(self):
        # The <style> element Mermaid emits for per-id CSS must stay.
        svg = (
            f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 10 10">'
            '<style>#m0 .node rect { fill: #4CAF50 }</style>'
            '<rect/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        assert "<style>" in out or "<style " in out
        assert ".node rect" in out

    def test_injects_xmlns_xlink_when_missing(self):
        # SVG uses xlink:href but declares no xmlns:xlink.
        svg = (
            f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 10 10">'
            '<use xlink:href="#sym"/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        # After parse+serialize, the xlink namespace must be declared and
        # the attribute kept. Check via lxml so we don't depend on the
        # literal prefix string.
        from lxml import etree as _e
        root = _e.fromstring(out)
        uses = root.findall(f".//{{{SVG_NS}}}use")
        assert uses
        assert uses[0].get(f"{{{XLINK_NS}}}href") == "#sym"

    def test_preserves_existing_xmlns_xlink(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}" '
            'id="m0" viewBox="0 0 10 10"><use xlink:href="#sym"/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        from lxml import etree as _e
        root = _e.fromstring(out)
        uses = root.findall(f".//{{{SVG_NS}}}use")
        assert uses[0].get(f"{{{XLINK_NS}}}href") == "#sym"


class TestNormalizeSvgIdRewrite:
    def test_rewrites_root_id(self):
        svg = f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 10 10"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        from lxml import etree as _e
        root = _e.fromstring(out)
        assert root.get("id") == "c01_0_mmd0"

    def test_extracts_numeric_suffix_from_original_id(self):
        svg = f'<svg xmlns="{SVG_NS}" id="mmd1028" viewBox="0 0 10 10"/>'
        out = normalize_svg_xhtml(svg, "c07_3")
        from lxml import etree as _e
        root = _e.fromstring(out)
        assert root.get("id") == "c07_3_mmd1028"

    def test_rewrites_internal_style_selector(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="mmd1028" viewBox="0 0 10 10">'
            '<style>#mmd1028 .node rect { fill: #4CAF50 }</style>'
            '<rect/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c07_3")
        assert "#c07_3_mmd1028 .node rect" in out
        assert "#mmd1028 " not in out

    def test_rewrites_derived_id_with_hyphen(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="mmd1028" viewBox="0 0 10 10">'
            '<marker id="mmd1028-flowchart-end"/>'
            '<path marker-end="url(#mmd1028-flowchart-end)"/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c07_3")
        assert 'id="c07_3_mmd1028-flowchart-end"' in out
        assert "url(#c07_3_mmd1028-flowchart-end)" in out
        assert "mmd1028-" not in out.replace("c07_3_mmd1028-", "")

    def test_rewrites_derived_id_with_underscore(self):
        svg = (
            f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 10 10">'
            '<g id="mmd0_flowchart-pointEnd"/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        assert 'id="c01_0_mmd0_flowchart-pointEnd"' in out

    def test_each_id_gets_its_own_prefix(self):
        # Every id gets its own prefixed form; mmd10 is not matched as a
        # prefix of mmd100 — they're independent declarations.
        svg = (
            f'<svg xmlns="{SVG_NS}" id="mmd10" viewBox="0 0 10 10">'
            '<g id="mmd100"/></svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        from lxml import etree as _e
        root = _e.fromstring(out)
        ids = [e.get("id") for e in root.iter() if e.get("id") is not None]
        assert "c01_0_mmd10" in ids
        assert "c01_0_mmd100" in ids  # NOT c01_0_mmd10 + "0"
        # No un-prefixed ids remain.
        assert "mmd10" not in ids
        assert "mmd100" not in ids

    def test_duplicate_ids_within_one_svg_get_suffixed(self):
        # Mermaid sometimes emits the same id on multiple elements in one
        # diagram (e.g. "node-undefined" on every fallback-classed node).
        # After prefixing, those would still collide in XHTML; deduplicate
        # by suffixing _2, _3, … so renamed ids are unique inside the SVG.
        svg = (
            f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 10 10">'
            '<g id="node-x"/><g id="node-x"/><g id="node-x"/>'
            '</svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        from lxml import etree as _e
        root = _e.fromstring(out)
        ids = [e.get("id") for e in root.iter() if e.get("id") is not None]
        # Root id + three now-unique derivatives of node-x.
        assert len(ids) == len(set(ids)), f"duplicate ids in SVG: {ids}"
        assert "c01_0_node-x" in ids
        assert "c01_0_node-x_2" in ids
        assert "c01_0_node-x_3" in ids

    def test_rewrites_mermaid_internal_ids(self):
        # Mermaid cache output contains ids like 'solidBottomArrowHead',
        # 'flowchart-D-5', and 'subGraph4' that do not contain the root
        # mmdN as a substring. These must be prefixed too, or two
        # diagrams in one chapter produce duplicate XHTML ids.
        svg = (
            f'<svg xmlns="{SVG_NS}" id="mmd1028" viewBox="0 0 10 10">'
            '<marker id="solidBottomArrowHead"/>'
            '<g id="subGraph4"/>'
            '<path marker-end="url(#solidBottomArrowHead)"/>'
            '</svg>'
        )
        out = normalize_svg_xhtml(svg, "c01_0")
        from lxml import etree as _e
        root = _e.fromstring(out)
        ids = {e.get("id") for e in root.iter() if e.get("id") is not None}
        assert ids == {"c01_0_mmd1028", "c01_0_solidBottomArrowHead", "c01_0_subGraph4"}
        # The url() reference is rewritten to match the renamed marker.
        assert "url(#c01_0_solidBottomArrowHead)" in out

    def test_does_not_touch_svg_without_id(self):
        svg = f'<svg xmlns="{SVG_NS}" viewBox="0 0 10 10"><rect/></svg>'
        out = normalize_svg_xhtml(svg, "c01_0")
        from lxml import etree as _e
        root = _e.fromstring(out)
        assert root.get("id") is None


class TestNormalizeSvgFallback:
    def test_invalid_svg_returns_placeholder(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        out = normalize_svg_xhtml("<svg><not closed", "c01_0")
        assert 'class="mermaid-broken"' in out
        assert "[diagram unavailable]" in out
        # The logged message mentions SVG parse failure; assert on a phrase
        # that actually appears in the log line we emit.
        assert any(
            "svg parse failed" in r.getMessage().lower()
            for r in caplog.records
        )


class TestRestoreSvgsAsImages:
    def test_replaces_placeholder_with_img(self):
        xhtml = '<div><!--__SVG_0__--></div>'
        svgs = [f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 10 10"/>']
        out, files = restore_svgs_as_images(xhtml, svgs)
        assert "<!--__SVG_0__-->" not in out
        import re as _re
        m = _re.search(
            r'<img src="(mermaid/[0-9a-f]{16}\.svg)" '
            r'width="10" height="10" alt="Diagram"/>',
            out,
        )
        assert m, f"no <img> found in {out!r}"
        assert len(files) == 1
        filename, svg_bytes = files[0]
        assert filename == m.group(1)
        # SVG file bytes start with XML prolog and carry case-preserved content.
        assert svg_bytes.startswith(b'<?xml')
        assert b'viewBox="0 0 10 10"' in svg_bytes
        # Width/height are stripped from the saved SVG so readers can render
        # at zoom-view resolution on demand instead of upscaling a bitmap.
        assert b' width=' not in svg_bytes
        assert b' height=' not in svg_bytes
        # Without a cross-SVG prefix, the id stays as declared in the source.
        assert b'id="mmd0"' in svg_bytes

    def test_handles_multiple_placeholders_in_order(self):
        xhtml = '<!--__SVG_0__--><p>middle</p><!--__SVG_1__-->'
        svgs = [
            f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 10 10"/>',
            f'<svg xmlns="{SVG_NS}" id="mmd1" viewBox="0 0 20 20"/>',
        ]
        out, files = restore_svgs_as_images(xhtml, svgs)
        assert '<p>middle</p>' in out
        assert len(files) == 2
        assert files[0][0] != files[1][0]
        assert out.count('<img src="') == 2

    def test_identical_svgs_share_one_file(self):
        # Same content -> same hash -> same filename -> only added once.
        # This is the payoff of dropping the cross-SVG id prefix: the
        # manifest doesn't duplicate identical diagrams.
        raw = f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 10 10"/>'
        xhtml = '<!--__SVG_0__--><!--__SVG_1__-->'
        out, files = restore_svgs_as_images(xhtml, [raw, raw])
        import re as _re
        refs = _re.findall(r'<img src="([^"]+)"', out)
        assert len(refs) == 2
        assert refs[0] == refs[1]
        assert len(files) == 1

    def test_distinct_svgs_get_distinct_files(self):
        a = f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 10 10"/>'
        b = f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 20 20"/>'
        out, files = restore_svgs_as_images(
            '<!--__SVG_0__--><!--__SVG_1__-->', [a, b]
        )
        assert len(files) == 2
        assert files[0][0] != files[1][0]

    def test_missing_svg_index_leaves_comment(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        out, files = restore_svgs_as_images(
            '<div><!--__SVG_5__--></div>', []
        )
        assert "<!--__SVG_5__-->" in out
        assert files == []
        assert any(
            "placeholder" in r.getMessage().lower() for r in caplog.records
        )

    def test_no_placeholders_returns_input_unchanged(self):
        out, files = restore_svgs_as_images('<div>no diagrams</div>', [])
        assert out == '<div>no diagrams</div>'
        assert files == []

    def test_svg_file_contains_xml_prolog(self):
        raw = f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 1 1"/>'
        _, files = restore_svgs_as_images('<!--__SVG_0__-->', [raw])
        content = files[0][1]
        assert content.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n')

    def test_custom_dir_prefix(self):
        raw = f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 1 1"/>'
        out, files = restore_svgs_as_images(
            '<!--__SVG_0__-->', [raw], dir_prefix="figures/mm"
        )
        assert 'src="figures/mm/' in out
        assert files[0][0].startswith("figures/mm/")


class TestPipelineIntegration:
    def test_case_survives_extract_xhtml_restore(self):
        # Skip the real mermaid-renderer: hand-craft the HTML that
        # replace_mermaid_blocks would produce, then run the rest of the
        # pipeline against it. The output chapter XHTML carries only an
        # <img> tag; the case-sensitive SVG content lives in a separate
        # file whose bytes are written opaquely by the EPUB writer.
        html = (
            '<article>'
            '<div class="mermaid-svg">'
            f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 100 50">'
            '<defs><clipPath id="clip0"><rect/></clipPath>'
            '<linearGradient id="g0"><stop/></linearGradient></defs>'
            '<path clip-path="url(#clip0)" fill="url(#g0)"/>'
            '</svg>'
            '</div>'
            '</article>'
        )
        html, svgs = extract_svgs(html)
        xhtml = html_to_xhtml(html)
        out, files = restore_svgs_as_images(xhtml, svgs)

        # Chapter XHTML has an <img>, not inline SVG.
        assert '<img src="mermaid/' in out
        assert '<svg' not in out

        # The separate SVG file has camelCase attributes preserved.
        assert len(files) == 1
        svg_bytes = files[0][1]
        assert b'viewBox="0 0 100 50"' in svg_bytes
        assert b'<clipPath' in svg_bytes
        assert b'<linearGradient' in svg_bytes

        # Ids stay as-declared (each SVG file is its own document, so no
        # cross-SVG prefixing is needed). References still resolve.
        assert b'id="mmd0"' in svg_bytes
        assert b'id="clip0"' in svg_bytes
        assert b'id="g0"' in svg_bytes
        assert b'url(#clip0)' in svg_bytes
        assert b'url(#g0)' in svg_bytes

    def test_two_diagrams_become_two_distinct_files(self):
        # Each SVG becomes its own file. Even when the source shared a
        # root id across diagrams, each file is self-contained so
        # cross-diagram collisions are structurally impossible.
        html = (
            f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 1 1">'
            '<marker id="solidBottomArrowHead"/>'
            '</svg>'
            '<hr/>'
            f'<svg xmlns="{SVG_NS}" id="mmd1" viewBox="0 0 1 1">'
            '<marker id="solidBottomArrowHead"/>'
            '</svg>'
        )
        html_p, svgs = extract_svgs(html)
        xhtml = html_to_xhtml(html_p)
        out, files = restore_svgs_as_images(xhtml, svgs)

        # Two <img> tags in the chapter, two separate SVG files.
        assert out.count('<img ') == 2
        assert len(files) == 2
        assert files[0][0] != files[1][0]

    def test_file_bytes_parse_as_standalone_svg(self):
        # Each EPUB svg file must be well-formed XML so EPUB readers can
        # render it from the <img src> reference.
        html = (
            f'<svg xmlns="{SVG_NS}" id="mmd0" viewBox="0 0 1 1">'
            '<style>#mmd0 .node rect { fill: #4CAF50 }</style>'
            '<rect/></svg>'
        )
        html_p, svgs = extract_svgs(html)
        xhtml = html_to_xhtml(html_p)
        _, files = restore_svgs_as_images(xhtml, svgs)
        from lxml import etree as _e
        root = _e.fromstring(files[0][1])
        assert root.tag == f"{{{SVG_NS}}}svg"
        # Scoped CSS still points to the (unchanged) root id.
        assert root.get("id") == "mmd0"
        styles = root.findall(f".//{{{SVG_NS}}}style")
        assert len(styles) == 1
        assert "#mmd0 .node rect" in styles[0].text


class TestDiagramSizeBehaviors:
    """Covers how normalize_svg_xhtml sizes diagrams for the EPUB viewport
    (550 wide x 600 tall cap). Every case applies a single uniform scale
    so aspect ratio is preserved, and never scales up from intrinsic."""

    def _dims(self, viewbox):
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="{viewbox}"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        import re as _re
        w = int(_re.search(r'\bwidth="(\d+)"', out).group(1))
        h = int(_re.search(r'\bheight="(\d+)"', out).group(1))
        return w, h

    # ---- natural-size cases (within bounds, no scaling) ----

    def test_tiny_diagram_preserved(self):
        # Already much smaller than the viewport — keeps intrinsic size.
        assert self._dims("0 0 10 10") == (10, 10)

    def test_small_diagram_preserved(self):
        assert self._dims("0 0 100 50") == (100, 50)

    def test_diagram_just_under_caps_preserved(self):
        # 549 x 599 fits within both caps — no scaling.
        assert self._dims("0 0 549 599") == (549, 599)

    def test_diagram_exactly_at_caps_preserved(self):
        # 550 x 600 exactly — scale factor 1.0, no shrinkage.
        assert self._dims("0 0 550 600") == (550, 600)

    # ---- width-limited cases (wider than tall) ----

    def test_wide_short_diagram_scaled_by_width(self):
        # Aspect 1100:300 → width-limited (550/1100=0.5). Height 300*0.5=150.
        assert self._dims("0 0 1100 300") == (550, 150)

    def test_extremely_wide_diagram_scaled_by_width(self):
        # 2500 x 200 → scale 0.22 → 550 x 44.
        assert self._dims("0 0 2500 200") == (550, 44)

    def test_barely_over_width_scaled_minimally(self):
        # 600 x 400 → width-limited (550/600=0.9167). Height 400*0.9167=366.
        assert self._dims("0 0 600 400") == (550, 366)

    # ---- height-limited cases (taller than wide) ----

    def test_tall_narrow_diagram_scaled_by_height(self):
        # 200 x 3000 → height-limited (600/3000=0.2). Width 200*0.2=40.
        assert self._dims("0 0 200 3000") == (40, 600)

    def test_extremely_tall_diagram_scaled_by_height(self):
        # 100 x 10000 → scale 0.06 → 6 x 600.
        assert self._dims("0 0 100 10000") == (6, 600)

    def test_barely_over_height_scaled_minimally(self):
        # 400 x 700 → height-limited (600/700=0.857). Width 400*0.857=342.
        assert self._dims("0 0 400 700") == (342, 600)

    # ---- both-over cases: uniform scale picks tighter constraint ----

    def test_square_large_diagram_scaled_by_height(self):
        # 1000 x 1000 → width-scale 0.55, height-scale 0.6 → pick 0.55
        # (tighter). Result 550 x 550.
        assert self._dims("0 0 1000 1000") == (550, 550)

    def test_large_rectangle_scaled_by_tighter_axis(self):
        # 800 x 1200 → width-scale 0.6875, height-scale 0.5 → pick 0.5.
        # Result 400 x 600.
        assert self._dims("0 0 800 1200") == (400, 600)

    def test_aspect_ratio_preserved_under_scale(self):
        # A 3:1 aspect viewBox must keep 3:1 rendering regardless of cap.
        w, h = self._dims("0 0 1500 500")
        assert abs(w / h - 3.0) < 0.05, f"aspect lost: {w}:{h}"

    # ---- intrinsic-upscale protection ----

    def test_tiny_diagram_not_scaled_up(self):
        # scale is clamped to <= 1.0 — tiny diagrams render tiny.
        w, h = self._dims("0 0 5 5")
        assert (w, h) == (5, 5)
        assert w < 550 and h < 600

    # ---- degenerate cases ----

    def test_zero_width_falls_back_to_no_size(self):
        # Degenerate viewBox: the early-return path leaves width/height unset.
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 0 100"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        import re as _re
        assert _re.search(r'\bwidth=', out) is None
        assert _re.search(r'\bheight=', out) is None

    def test_missing_viewBox_leaves_dimensions_alone(self):
        # No viewBox → no derived pixel sizing.
        svg = f'<svg xmlns="{SVG_NS}" id="m0"><rect/></svg>'
        out = normalize_svg_xhtml(svg, "c01_0")
        import re as _re
        assert _re.search(r'\bwidth=', out) is None
        assert _re.search(r'\bheight=', out) is None

    def test_malformed_viewBox_falls_back_to_no_size(self):
        # Non-numeric viewBox values — ValueError path leaves dimensions alone.
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 nope bad"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        import re as _re
        assert _re.search(r'\bwidth=', out) is None
        assert _re.search(r'\bheight=', out) is None

    def test_float_viewBox_truncates_to_int_pixels(self):
        # Real Mermaid output is often floats like "0 0 591.265 812".
        # The scale + int() cast produces integer pixel counts.
        svg = f'<svg xmlns="{SVG_NS}" id="m0" viewBox="0 0 591.265 812"/>'
        out = normalize_svg_xhtml(svg, "c01_0")
        # min(1.0, 550/591.265, 600/812) = min(1, 0.9302, 0.7389) = 0.7389
        # → width = int(591.265 * 0.7389) = 437
        #   height = int(812 * 0.7389) = 600
        import re as _re
        w = int(_re.search(r'\bwidth="(\d+)"', out).group(1))
        h = int(_re.search(r'\bheight="(\d+)"', out).group(1))
        assert h == 600
        assert 436 <= w <= 438  # integer-truncation tolerance

    def test_all_outputs_never_exceed_caps(self):
        # Sweep a representative grid; no combination produces a larger
        # rendered size than the configured caps.
        for vb_w in (5, 50, 400, 550, 600, 1100, 5000):
            for vb_h in (5, 50, 400, 600, 700, 2000, 10000):
                w, h = self._dims(f"0 0 {vb_w} {vb_h}")
                assert w <= 550, f"vb={vb_w}x{vb_h} -> w={w} > 550"
                assert h <= 600, f"vb={vb_w}x{vb_h} -> h={h} > 600"


class TestChapterSlugFor:
    def test_prepends_ch_to_stem(self):
        assert chapter_slug_for("07-bionic-and-linker.md") == "ch07-bionic-and-linker"

    def test_never_starts_with_digit(self):
        # All AOSP book filenames follow the NN-slug.md convention, which
        # would produce invalid CSS identifiers without a non-digit prefix.
        for src in ("01-intro.md", "42.md", "09-abc.md", "00-frontmatter.md"):
            assert not chapter_slug_for(src)[0].isdigit()

    def test_strips_directory_prefix(self):
        # Path.stem handles nested paths and the final extension only.
        assert chapter_slug_for("part1/03-foo.md") == "ch03-foo"

    def test_letter_leading_stem_still_gets_prefix(self):
        # For consistency — the prefix applies unconditionally. The goal
        # is a single rule, not a special-case dance.
        assert chapter_slug_for("A-appendix-key-files.md") == "chA-appendix-key-files"
