# Mermaid Syntax Reference

Mermaid's parser is stricter than most Markdown authors expect. These rules prevent silent rendering failures — diagrams that just show up blank with no error message.

## Quoting Rules

Any node label containing special characters must be wrapped in double quotes. Mermaid interprets unquoted `()` as round-node syntax, `|` as edge-label delimiters, and `<br/>` as raw HTML in non-HTML contexts.

### Diamond nodes
```
Bad:  {text with parens()}
Good: {"text with parens()"}

Bad:  {text<br/>more text}
Good: {"text<br/>more text"}
```

### Square bracket nodes
```
Bad:  NODE[text(stuff)]
Good: NODE["text(stuff)"]

Bad:  NODE[text<br/>more]
Good: NODE["text<br/>more"]
```

### Edge labels
```
Bad:  -->|func()|
Good: -->|"func()"|
```

## Diagram-Specific Rules

### sequenceDiagram
`<br/>` in `participant` declarations breaks rendering entirely. Use spaces instead:

```
Bad:  participant App as Application<br/>(App Process)
Good: participant App as Application (App Process)
```

`<br/>` in message labels and `Note` blocks is fine.

### stateDiagram-v2
Parentheses in transition labels cause parse errors — and **this is by far the most common Mermaid breakage in this book** (a single audit pass fixed 100+ instances across 25+ chapters). Quoting does not save you here; you must rewrite without parens:

```
Bad:  State1 --> State2 : CanvasContext::create()
Good: State1 --> State2 : CanvasContext create

Bad:  Idle --> Running : start() called
Good: Idle --> Running : start called

Bad:  Stopped --> Idle : finish (while paused)
Good: Stopped --> Idle : finish, while paused
```

`<br/>` *does* work inside stateDiagram-v2 transition labels in Mermaid 11.x (it wraps the label across lines), so a long label like `PENDING --> READY : onResponse<br/>has data` renders fine. Don't strip `<br/>` reflexively — only parentheses are the parse-killer here.

Also strip `;` from transition labels (Mermaid treats it as a statement separator) and avoid raw newline characters; use `<br/>` for visual line breaks.

### flowchart / graph
`<br/>` in node labels is valid when the label is quoted:
```
Good: A["First line<br/>Second line"]
```

Subgraph names with spaces need explicit IDs:
```
Bad:  subgraph Home Screen
Good: subgraph HS["Home Screen"]
```

## Common Parse Errors

| Error message | Cause | Fix |
|--------------|-------|-----|
| `Expecting 'SQE', 'PE'...` | Unquoted `()` in node label | Quote the label |
| `Parse error on line N` near `<br/>` | `<br/>` in participant or unquoted label | Quote or remove |
| `No diagram type detected` | Empty or malformed mermaid block | Check for unclosed fences |
| Diagram renders blank (no error) | Syntax valid but semantically wrong | Check node/edge references match |

## Silent Renderer Bugs

These don't trigger parse errors — Mermaid happily renders the diagram, but the output is wrong in a way you only catch by looking at the PNG. Both bit this book repeatedly during the audit.

### Literal `\n` in stateDiagram and sequenceDiagram labels

In flowchart and `graph` node/edge labels Mermaid treats `\n` as a line break. **In `stateDiagram-v2` transition labels and `sequenceDiagram` messages it does not** — the `\n` shows up in the output as the literal characters `\n`. Always use `<br/>` in those contexts:

```
Bad (stateDiagram-v2):
  Idle --> Active : trigger\nbegin work

Good:
  Idle --> Active : trigger<br/>begin work

Bad (sequenceDiagram message):
  A->>B: Step 1\nStep 2

Good:
  A->>B: Step 1<br/>Step 2
```

The same `\n` in a `note` block inside a stateDiagram also renders literally — use `<br/>`. (One audit pass found 5+ instances of this across chapters.)

### `<word>` placeholders get stripped as HTML tags

In flowchart and `graph` node and edge labels, the SVG renderer treats anything matching `<...>` as an HTML tag and silently drops it. Authors often write `<name>`, `<pid>`, `<uuid>`, `<service>` as plain-English placeholders, expecting them to render verbatim. They don't — the placeholder vanishes and the label reads `Mount at /apex//` instead of `Mount at /apex/<name>/`.

Always use brace or bracket placeholders inside flowchart labels:

```
Bad:   N["Mount at /apex/<name>/"]
Good:  N["Mount at /apex/{name}/"]

Bad:   A -->|"start <service>"| B
Good:  A -->|"start {service}"| B
```

`sequenceDiagram` messages and class-diagram annotations (e.g. `<<abstract>>`) preserve `<word>` correctly — the bug is specific to flowchart/graph node and edge labels. (One audit pass found 13+ instances across chapters.)
