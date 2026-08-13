// Typography and structural polish for Mermaid diagrams that CSS variables
// alone can't express: uppercase mono zone labels, rounded node corners,
// hairline strokes, muted edge labels. Material renders each diagram into an
// (opened — see overrides/main.html) shadow root, which page stylesheets
// can't reach, so this injects a <style> into every diagram's shadow root
// after render. Colors reference the --emu-mermaid-* / --md-mermaid-*
// variables from stylesheets/mermaid-theme.css, which inherit through the
// shadow boundary and stay dark-mode reactive.
//
// Font sizes only ever shrink from mermaid's 16px layout size: foreignObject
// label boxes are measured before this CSS applies, so growing text would
// overflow them (overflow:visible below is a safety net, not a license).
;(function () {
  var MONO = "var(--md-code-font-family, ui-monospace, monospace)"
  var CSS =
    'foreignObject{overflow:visible}' +
    // flowchart nodes: white cards, near-black hairline, rounded
    '.node rect{rx:6px;ry:6px;stroke-width:1px}' +
    '.nodeLabel{font-size:14px}' +
    // subgraph zones: quiet wash + small-caps mono label
    '.cluster rect{fill:var(--emu-mermaid-cluster-bg)!important;' +
      'stroke:var(--emu-mermaid-cluster-border)!important;rx:8px;ry:8px}' +
    '.cluster-label .nodeLabel{font-family:' + MONO + ';font-size:10.5px;' +
      'font-weight:500;letter-spacing:.14em;text-transform:uppercase;' +
      'color:var(--emu-mermaid-zone-label-color)!important}' +
    // edges: hairlines with small muted mono annotations
    '.edgePath .path,.flowchart-link{stroke-width:1.1px}' +
    '.edgeLabel .nodeLabel,span.edgeLabel{font-family:' + MONO + ';' +
      'font-size:11.5px;color:var(--emu-mermaid-edge-label-color)!important}' +
    // sequence diagrams: rounded actors, quiet activations, smaller text.
    // .actor-line is missing from Material's themeCSS, so mermaid's default
    // purple leaks through without this override.
    '.actor{rx:6px;stroke-width:1px}' +
    '.actor-line{stroke:var(--md-mermaid-sequence-actor-line-color)!important}' +
    'text.actor>tspan{font-size:14px}' +
    '.messageText{font-size:12.5px;font-family:' + MONO + '!important}' +
    '.noteText>tspan,.labelText>tspan,.loopText>tspan{font-size:12.5px}' +
    '.activation0,.activation1,.activation2{' +
      'fill:var(--emu-mermaid-activation-bg)!important;' +
      'stroke:var(--md-mermaid-edge-color)!important;stroke-width:0.8px}'

  function attach() {
    var els = document.querySelectorAll('div.mermaid')
    for (var i = 0; i < els.length; i++) {
      var root = els[i].shadowRoot
      if (!root || root.__emuThemed || !root.querySelector('svg')) continue
      var style = document.createElement('style')
      style.textContent = CSS
      root.appendChild(style)
      root.__emuThemed = true
    }
  }

  attach()
  // Diagrams render lazily and on SPA navigation; cheap periodic re-attach,
  // same pattern as mermaid-zoom.js.
  setInterval(attach, 1000)
})()
