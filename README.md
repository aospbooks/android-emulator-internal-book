# Android Emulator Internals

**A Developer's Guide to the Android Emulator**

A technical book covering the Android Emulator from the host process down to the
guest kernel — the QEMU fork, CPU acceleration, the `android-emu` core, the
gfxstream graphics pipeline, networking, snapshots, the gRPC control plane, and
the Qt/WebRTC user interfaces — with claims referencing real source paths in the
emulator tree.

**Read online:** <https://aospbooks.github.io/android-emulator-internal-book/>

> If you spot errors, missing details, or have suggestions, please [open an issue](https://github.com/aospbooks/android-emulator-internal-book/issues) or submit a pull request — feedback from emulator developers and enthusiasts is very welcome.

<!-- --8<-- [start:coverage] -->
## What This Book Covers

28 chapters organized bottom-to-top through the emulator stack — from the QEMU
machine model up through the host renderer, the streaming UIs, and the
crosvm-based Cuttlefish virtual device:

| Part | Ch. | Topics | Reviewed |
|------|-----|--------|----------|
| Front | 0 | Frontmatter | ✗ |
| I | 1 | Introduction (host/guest split, architecture) | ✗ |
| I | 2 | Source Code & Build System (repo manifest, CMake/Bazel) | ✗ |
| I | 3 | Running the Emulator (launcher, AVDs, config) | ✗ |
| II | 4 | The QEMU Fork (ranchu/goldfish, qemu2-glue) | ✗ |
| II | 5 | CPU Acceleration (KVM/HVF/WHPX/AEHD/TCG) | ✗ |
| II | 6 | Virtual Hardware & virtio | ✗ |
| III | 7 | android-emu Architecture & Lifecycle | ✗ |
| III | 8 | Console & gRPC Control Plane | ✗ |
| III | 9 | Snapshots & Quickboot | ✗ |
| III | 10 | Sensors, Battery & Location | ✗ |
| IV | 11 | Graphics Architecture (gfxstream) | ✗ |
| IV | 12 | Guest GPU Drivers | ✗ |
| IV | 13 | Host Rendering (libOpenglRender/ANGLE/mesa) | ✗ |
| IV | 14 | gfxstream Protocol | ✗ |
| V | 15 | Audio | ✗ |
| V | 16 | Camera | ✗ |
| V | 17 | Display & Multi-Display | ✗ |
| VI | 18 | Networking (slirp/netsim) | ✗ |
| VI | 19 | Bluetooth (rootcanal) | ✗ |
| VI | 20 | ADB Integration | ✗ |
| VI | 21 | Modem & Telephony | ✗ |
| VII | 22 | The Qt UI | ✗ |
| VII | 23 | WebRTC & the Embedded Emulator | ✗ |
| VIII | 24 | System Images & the Goldfish HAL | ✗ |
| VIII | 25 | Guest Boot | ✗ |
| IX | 26 | Cuttlefish & crosvm (the crosvm-based virtual device) | ✗ |
| X | 27 | Testing | ✗ |
| X | 28 | Debugging, Tracing & Crash Reporting | ✗ |
| App. | A | Paravirtualization from Xen to Android | ✗ |
| App. | B | Key Files Reference | ✗ |
| App. | C | Glossary | ✗ |

✗ = not yet reviewed by a human; published openly for community review.
<!-- --8<-- [end:coverage] -->

## How to Give Feedback

- **Found an error?** Open an issue describing the chapter, section, and what's wrong.
- **Have a suggestion?** Pull requests are welcome — even small fixes like typos or broken source paths.
- **Know a subsystem deeply?** We especially value feedback from engineers who work on specific emulator components.

## Quick Start

### Docker

```bash
./serve.sh           # start (http://localhost:8001)
./serve.sh off       # stop
./serve.sh status    # check if running
./serve.sh pdf       # build PDF → site/android-emulator-internals.pdf
./serve.sh epub      # build EPUB → site/android-emulator-internals.epub
./serve.sh png NN-slug.md   # render a chapter's Mermaid blocks to PNG for visual review
```

The `pdf`/`epub` commands stop any running server, then build all chapters into a
single document with rendered Mermaid diagrams (uses Playwright/Chromium).

### Without Docker

```bash
# Install (one-time)
pip install mkdocs-material pymdown-extensions

# Create symlinks (one-time)
mkdir -p docs
for f in [0-9]*.md [A-Z]-*.md index.md; do ln -sf "../$f" "docs/$f"; done

# Start
mkdocs serve                       # http://127.0.0.1:8000

# Build static site
mkdocs build                       # output in site/
```

Open **http://localhost:8001** — chapters in the sidebar, Mermaid renders live, hot-reload on edits.

## GitHub Actions

Tests `mkdocs build` on push to `main` and PRs (~2 min); deploys to GitHub Pages on push to `main`.

## Project Structure

```
[0-9]*.md                  chapter files
[A-C]-appendix-*.md        appendix files
index.md                   Website homepage
mkdocs.yml                 MkDocs config (Material theme + Mermaid)
docs/                      Symlinks for MkDocs (gitignored)
mkdocs-mermaid-renderer/   Shared Mermaid SVG renderer (Playwright + cache)
mkdocs-pdf-generate/       MkDocs plugin: PDF export
mkdocs-epub-generate/      MkDocs plugin: EPUB export
Dockerfile                 python:3.12-slim + Playwright + MkDocs plugins
docker-compose.yml         serve / build-site / build-pdf / build-epub
tools/render_mermaid_png.py  Mermaid → PNG renderer for visual review
CLAUDE.md                  Project rules for AI agents
.claude/skills/            book-writer
.github/workflows/         CI: mkdocs build test + Pages deploy
```

## License

This project is licensed under the [Apache License 2.0](LICENSE), matching the
license of the Android Emulator and the Android Open Source Project it analyzes.
