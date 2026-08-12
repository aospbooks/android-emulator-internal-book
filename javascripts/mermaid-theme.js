// Structural polish for Mermaid diagrams that CSS variables alone can't
// express: rounded node corners, hairline strokes, quiet cluster washes.
// Material renders each diagram into an (opened — see overrides/main.html)
// shadow root, which page stylesheets can't reach, so this injects a <style>
// into every diagram's shadow root after render. Colors reference the
// --emu-mermaid-* / --md-mermaid-* variables from stylesheets/mermaid-theme.css,
// which inherit through the shadow boundary and stay dark-mode reactive.
;(function () {
  var CSS =
    '.node rect{rx:6px;ry:6px;stroke-width:1px}' +
    '.cluster rect{fill:var(--emu-mermaid-cluster-bg)!important;' +
      'stroke:var(--emu-mermaid-cluster-border)!important;rx:8px;ry:8px}' +
    '.edgePath .path,.flowchart-link{stroke-width:1.1px}' +
    '.actor{rx:6px;stroke-width:1px}' +
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
