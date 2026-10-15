FROM python:3.12-slim

# Playwright + Chromium render Mermaid diagrams to PNG for `./serve.sh png`
# (largest layer, changes least often)
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium

RUN pip install --no-cache-dir properdocs mkdocs-material pymdown-extensions

# Mermaid SVG renderer used by tools/render_mermaid_png.py
COPY mkdocs-mermaid-renderer /opt/mkdocs-mermaid-renderer
RUN pip install --no-cache-dir /opt/mkdocs-mermaid-renderer

WORKDIR /book
COPY . .

EXPOSE 8001
CMD ["properdocs", "serve", "-a", "0.0.0.0:8001"]
