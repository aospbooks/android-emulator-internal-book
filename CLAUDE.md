# Android Emulator Internals Book

28 chapters + 2 appendices, source-referenced against the Android Emulator tree,
served as a MkDocs Material website with Mermaid diagrams.

## Quick Start

```bash
docker compose build
docker compose up -d serve         # http://localhost:8001
```

## Privacy & Path Rules (READ FIRST)

1. **Never expose a local absolute path or personal information in committed
   content.** No `/home/<user>/...`, no machine names, no usernames, no email
   addresses anywhere in chapters, config, diagrams, or commit messages. Source
   references must be **repo-relative paths within the emulator tree**, e.g.
   `external/qemu/android/android-emu/android/console.cpp`, never
   `/home/.../emu-main-dev/external/qemu/...`.
2. The emulator source lives outside this repo. When citing it, strip everything
   up to **and including** the superproject root directory so the path starts at
   a top-level project dir (`external/`, `hardware/`, `tools/`, `device/`,
   `frameworks/`, `packages/`). The local checkout's root directory name must
   never appear in committed content — only the in-tree project-relative path.

## Writing Rules

1. Chapters: `NN-slug.md`, titles: `# Chapter N: Title` — colon only, never `--` or `—`
2. Section numbers: manual `## N.1`, `### N.1.2` matching filename
3. No duplicate section numbers within a chapter (watch for this when inserting new sections)
4. Mermaid: quote labels with `()`, `<br/>`, `|`; no `<br/>` in `participant` lines; **no parens in `stateDiagram-v2` transition labels** (`State1 --> State2 : foo()` breaks parsing — drop the parens)
5. Descriptive heading before each mermaid block
6. Source refs: real emulator paths with line numbers, repo-relative (see Privacy & Path Rules)
7. The body of every chapter ends with "Try It" then "Summary" — nothing else comes after Summary, **except** an optional final "Key Source Files" table, which may sit after Summary as a final reference.
8. **Do not add epigraph blockquotes at the top of chapters.** The chapter goes straight into its introductory paragraph after the title.
9. **Verify mermaid format parses after every edit.** Run `./serve.sh png NN-slug.md` on every chapter whose Mermaid blocks you touched and confirm the output reports `errors=0`. The CI `mkdocs build` does NOT validate Mermaid (the live site renders it client-side), so a parse error reaches readers as a "Syntax error" banner with no build-time signal. Treat `errors=0` as a hard precondition.
10. **Visually verify mermaid diagrams after writing or editing them.** Parse-clean is not enough — diagrams can render with text overflowing rectangles, overlapping nodes, or be factually wrong about the architecture. After rule 9 passes, inspect each PNG under `.mermaid-png/<slug>/`. Check: (a) every label fits inside its shape; (b) no nodes or edge labels overlap; (c) the boxes, arrows, and grouping match the architecture the prose describes.

## CI

GitHub Actions runs `mkdocs build` on push/PR (~2 min) and deploys to GitHub
Pages on push to `main`.

## Commit Rules

Do not add a `Co-Authored-By` trailer when creating commits. Commits should have
a plain author and no AI/tool attribution footer.

## Skills

- `.claude/skills/book-writer/SKILL.md` — chapter structure, content guidelines, MkDocs sync
  - `references/mermaid-syntax.md` — detailed quoting rules and common parse errors
