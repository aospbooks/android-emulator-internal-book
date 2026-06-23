#!/usr/bin/env bash
#
# Usage:
#   ./serve.sh        Start the website (http://localhost:8001)
#   ./serve.sh on     Same as above
#   ./serve.sh off    Stop the website
#   ./serve.sh status Check if running
#   ./serve.sh pdf    Build the PDF (outputs site/android-emulator-internals.pdf)
#   ./serve.sh epub   Build the EPUB (outputs site/android-emulator-internals.epub)
#   ./serve.sh png NN-slug.md [...]
#                     Render mermaid blocks in the given chapter(s) to PNG
#                     under .mermaid-png/<slug>/NN-<hash>.png. Use these for
#                     visual review (text fits in shapes, no overlap, diagram
#                     content matches the surrounding prose).
#                     Pass --all instead of a chapter to render every chapter.
#
set -euo pipefail

case "${1:-on}" in
  on|start)
    docker compose down 2>/dev/null
    docker compose build serve
    docker compose up -d serve
    echo -n "Waiting for site"
    for i in $(seq 1 30); do
      if curl -s -o /dev/null http://localhost:8001 2>/dev/null; then
        echo ""
        echo "Website ready at http://localhost:8001"
        exit 0
      fi
      echo -n "."
      sleep 1
    done
    echo ""
    echo "Website started but may still be building (check: docker compose logs serve)"
    ;;
  off|stop)
    docker compose down
    echo "Website stopped"
    ;;
  status)
    docker compose ps serve
    ;;
  pdf)
    docker compose down 2>/dev/null
    echo "Building PDF (pre-rendered mermaid diagrams, cached)..."
    docker compose build build-pdf
    docker compose run --rm build-pdf
    echo "PDF generated: site/android-emulator-internals.pdf"
    ;;
  epub)
    docker compose down 2>/dev/null
    echo "Building EPUB (pre-rendered mermaid diagrams, cached)..."
    docker compose build build-epub
    docker compose run --rm build-epub
    echo "EPUB generated: site/android-emulator-internals.epub"
    ;;
  png)
    shift
    if [ $# -eq 0 ]; then
      echo "Usage: $0 png NN-slug.md [NN-slug.md ...] | --all" >&2
      exit 1
    fi
    docker compose build serve >/dev/null
    docker run --rm -v "$PWD":/book -w /book book-serve \
      python3 tools/render_mermaid_png.py "$@"
    echo "PNGs written under .mermaid-png/"
    ;;
  *)
    echo "Usage: $0 [on|off|status|pdf|epub|png NN-slug.md]"
    exit 1
    ;;
esac
