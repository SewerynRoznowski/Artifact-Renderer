# mbse-artifact-viewer

Renders a folder of engineering documentation — a WireViz harness, notes,
a drawing — from a small `artifact.yaml` manifest that says what is in the
folder and in what order.

It knows nothing about Capella. Point it at a directory; there is no
model, no uuid, and no `capellambse` anywhere in it. That is the point: an
electrical engineer can check their own harness renders correctly inside
their own repo, before it is ever committed or pulled into an MBSE
project. Resolving *which* folder belongs to which model element is the
consuming application's job.

See [SPEC.md](SPEC.md) for the design and the reasoning behind it.

## Install

```sh
pip install -e ".[all]"         # or pick the extras you need
```

The extras are optional on purpose. `[wireviz]` renders harness diagrams
and also needs [Graphviz](https://graphviz.org/download/) on `PATH`;
`[pdf]` is only needed to show a *page selection* from a PDF, since a
whole document is served as-is. A missing extra degrades to a placeholder
on those sections alone — the rest of the page still renders.

## Use

```sh
mav serve  examples/Harness-001      # browse it, live-reloading as you edit
mav check  examples/Harness-001      # anything declared that didn't render?
mav render examples/Harness-001 -o harness.html
```

`serve` opens the page in your default browser and holds the terminal
until Ctrl-C. Pass `--no-open` to skip that — on a headless box or over
SSH there is nothing to open, which is a normal outcome rather than an
error: it says so and carries on serving.

`serve` browses the whole checkout, not just the folder you name. Every
directory answers: one holding an `artifact.yaml` renders as a page, any
other lists the artifacts beneath it with their descriptions and a note on
any that have problems. So `mav serve` on its own, at the root of a repo,
gives you an index of everything in it, and the folder you name is just
where it opens.

`serve` starts on port 8000, or the next free one if that is taken — on
Windows, Hyper-V and WSL reserve whole port ranges, and a reserved port
refuses the bind outright rather than reporting itself as in use. Ask for
a specific port with `-p 8931`; an explicitly requested port is never
silently swapped, since a URL you already have open would then be quietly
wrong.

`check` exits non-zero if something declared didn't render, so it works in
a pre-commit hook or CI:

```sh
mav check "$folder" || exit 1
```

## The manifest

```yaml
name: Harness-001
description: 4-wire power/CAN harness between two Molex KK 254 connectors.
doc: overview.md          # long-form intro, rendered above the sections

sections:
  - type: wireviz
    path: harness.yaml
    description: Wire colours and pin assignments as built.

  - type: markdown
    path: ../datasheets/molex-kk-254.md    # shared, not a copy
    description: Connector datasheet extract.
```

`sections:` is an ordered list, not a dict of typed keys, so order is
yours to control and a type may repeat (a PDF, then a 3D model, then
another PDF).

`description` is a single line — the label an index listing or a search
result shows. `doc` points at a Markdown file for prose of any real
length, because writing that inside YAML is miserable. They layer rather
than replace: `description` is the lede, `doc` the body. Both work on a
section as well as on the artifact.

### Section types

| Type | Renders | Options |
|---|---|---|
| `wireviz` | WireViz YAML → SVG | `wrap`, `designator`, `prepend` |
| `markdown` | Markdown → HTML | — |
| `html` | a fragment inline, a document in a frame | `height` |
| `pdf` | an embedded PDF viewer | `pages`, `height` |
| `3dmodel` | glTF in a Three.js viewer | `camera`, `up`, `height` |
| `jupyter` | a notebook's outputs | `cells`, `tags`, `include_source` |

A `wireviz` section takes either a complete harness or a bare connector
template — the kind that only defines a reusable YAML anchor. A template
is detected and wrapped in a minimal self-referencing `connections:` block
before rendering, because WireViz silently drops any connector that no
connection set mentions. `wrap: never` turns that off; `designator: X2`
changes the reference designator it draws under.

The other half of that arrangement is `prepend:`. WireViz has no
cross-file `!include`, so a harness that borrows a connector definition
by YAML anchor is not valid on its own — the template's text has to go in
front of it before parsing, which is what WireViz's own `--prepend` flag
does. `prepend: ../../connectors/Connector-001/connector.yaml` means one
connector definition serves every harness that terminates in it, and
changing the pinout there changes all of them.

A `pdf` section with `pages: "14-15"` shows *only* those pages: the
selection travels in the URL and the serving side extracts them, so what
reaches the browser is a two-page document, not a 34-page one scrolled to
page 14. Pages past the end of the document are dropped with a warning; a
selection that cannot be parsed is an error, because silently showing all
34 pages when two were asked for is the worse outcome.

Unlike Markdown or a diagram, a PDF cannot be inlined into the page — a
browser needs a real URL to point its viewer at. So `pdf` needs the
consumer to offer a file-serving route (`url_for`, below). The CLI has
one; a consumer without one gets a placeholder saying so rather than an
empty frame.

An `html` section takes both kinds of HTML file. A **fragment** — a bare
`<svg>`, a table, some markup — drops straight into the page. A
**complete document** gets a frame of its own instead, because its
`<head>` is usually where the thing that makes it legible lives: an
nbconvert notebook export is 276 KB of stylesheet and 44 KB of content.
Inside a frame that stylesheet applies to itself and cannot reach the
page around it.

A `jupyter` section shows a notebook's **results** — prose and outputs,
no code. That is the opposite of what a notebook viewer usually does, and
deliberate: an analysis notebook is a working document full of imports
and scratch variables, and a reviewer wants the diagram, the table and
the number that came out. `include_source: true` brings the code back;
`cells: "6-9"` and `tags: [report]` narrow it down. Images are embedded
straight from the `.ipynb`, so unlike `pdf` and `3dmodel` this type needs
no file-serving route at all.

A `3dmodel` section takes **glTF only** — `.glb` (everything in one
file) or `.gltf`. No STEP, no conversion: this is a reference view so a
reviewer can see *which* part is being discussed, while the detail lives
in the drawings and PDFs beside it. Converting STEP server-side would put
a few hundred megabytes of OpenCascade into every deployment to produce a
picture an export step gives you for free.

Export in **metres** (glTF's convention; CAD gives you millimetres) and,
if you can, **Y-up**. When the export lands Z-up anyway — as STEP always
does — `up: z` stands it upright.

If your source of truth is STEP, [tools/step_to_glb.py](tools/step_to_glb.py)
tessellates it at build time (`pip install cascadio`), which is where that
work belongs: once, in the repo that owns the CAD, rather than on every
page view in a deployment that would then need a CAD kernel.
[examples/Converted-CAD](examples/Converted-CAD) is the worked example. `camera` is the *direction* to look from rather than a position,
so the same `[1, 1, 1]` frames a 4 mm connector and a 3 m panel — the
distance is fitted to the model.

An option this renderer doesn't understand is a warning, never an error,
so a manifest written against a newer version stays usable on an older
one.

### When something is missing

A page renders as much as it can. One bad section never takes down the
sections around it: it is replaced, in place, by a note saying what was
declared and what went wrong. Only an unreadable `artifact.yaml` is fatal,
and only for that one folder.

Silence is the failure mode this avoids. An artifact that was declared and
isn't there has to be *visible* on the page, not merely absent from it.

## Embedding it

A consuming application supplies its own file access, so the folder need
not be on a local disk — Model Explorer reads through capellambse's
resource handler, where a git- or HTTP-backed model has no local path:

```python
from mbse_artifact_viewer import render_artifact

result = render_artifact(source, "artifacts/Harness-001")
embed(result.head, result.html)          # a fragment, not a whole page
for diagnostic in result.diagnostics:    # nothing is swallowed
    logger.warning("%s", diagnostic)
```

`source` is anything with `read_bytes(path)` and `exists(path)` taking
root-relative POSIX paths — `LocalFileSource` is built in. Add an
optional `url_for(path, params)` returning a URL the browser can fetch,
and `pdf` and `3dmodel` sections work too — both are fetched by the
browser rather than inlined. Without it they report that the consumer has
no file-serving route, rather than showing an empty frame.

Include `mbse_artifact_viewer.STYLESHEET` once in the host page, and emit
`result.head` above the fragment — some section types need page-level
markup (the 3D viewer's import map) that must appear once however many
sections use it. `.document()` does both for you if you want a standalone
file instead.

### Adding a section type

One registry entry. No page template is touched:

```python
from mbse_artifact_viewer import RenderContext, renderer

@renderer("step", options={"units"})
def render_step(ctx: RenderContext) -> str:
    text = ctx.read_text(ctx.require_path())
    return f"<pre>{len(text.splitlines())} lines of STEP</pre>"
```

## Examples

Six working examples. None of them are broken — they are what to copy:

| Folder | Shows |
|---|---|
| [examples/Harness-001](examples/Harness-001) | a WireViz harness, a `doc:` intro, a shared datasheet reached with `../`, and one page of a shared PDF |
| [examples/Connector-001](examples/Connector-001) | a bare connector template, auto-wrapped so it draws on its own |
| [examples/Compliance-CDS](examples/Compliance-CDS) | an 8 MB, 34-page specification shown twice — trimmed to the two pages that matter, and in full |
| [examples/Converted-CAD](examples/Converted-CAD) | three STEP files tessellated to glTF at build time — including a 14 MB, 483-part assembly |
| [examples/ANA-001](examples/ANA-001) | a capella-cubed analysis four ways: the generated report, the notebook's results, the working with code, and nbconvert's export |
| [examples/Bracket-Assembly](examples/Bracket-Assembly) | a mechanical part three ways: an SVG drawing, a Z-up glTF model in the 3D viewer, and page 1 of its torque schedule |

Breakage lives apart, in [examples/broken/](examples/broken), so it is
never in doubt whether an example is meant to look like that:

| Folder | What is wrong |
|---|---|
| [Missing-Files](examples/broken/Missing-Files) | every section names a file that isn't there |
| [Unknown-Types](examples/broken/Unknown-Types) | a typo, a type nobody implements, and one that isn't built yet |
| [Bad-Options](examples/broken/Bad-Options) | options that are unknown, malformed, or out of range |

The example assets are generated, not hand-committed binaries — see
[tools/](tools) for the scripts that build the bracket `.glb`, the torque
spec `.pdf`, and the glTF converted from the STEP files in
[examples/steps/](examples/steps).

## Development

```sh
pip install -e ".[all]" pytest
pytest
```
