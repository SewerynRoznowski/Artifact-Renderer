# Artifact Rendering System — Design Spec

## Motivation

Physical interfaces (links, ports) need supporting documentation — wiring
diagrams, connector pinouts, mechanical drawings, 3D models, datasheets —
that shouldn't live inside the Capella model itself. Different engineering
disciplines (electrical, mechanical, software) may own this content in
their own separately-versioned repositories. This spec covers how that
content is structured, linked to model elements, and rendered — both
inside Model Explorer and standalone, before it's ever committed.

## Scope: the package knows nothing about Capella

The package's whole world is *a folder containing an `artifact.yaml`*.
It never sees a uuid, an `.aird`, a PVMT property, or a `capellambse`
object, and it must not grow a dependency that would let it. A discipline
team rendering their own PCB repo locally has no Capella model to hand
and shouldn't need one.

Everything Capella-shaped is the **consumer's** job:

| Concern | Owner |
|---|---|
| `artifact.yaml` parsing, section registry, rendering, path resolution | the package |
| uuid → folder resolution (`artifacts/index.yaml`) | Model Explorer |
| the PVMT `Interface Type` enum | Model Explorer |
| which folder to hand the renderer, and where to embed the output | the consumer |

The PVMT enum was once used for render dispatch. The manifest now
describes what to render, so the package has no use for it — whether
Model Explorer keeps it as descriptive/searchable metadata is a decision
for that repository, not this one.

The rest of this document describes both sides, because the system has to
work end to end; the table above says which half each section belongs to.

## Artifact index (`artifacts/index.yaml`) — consumer side

Not part of the package. Lives at the model repository's root, alongside
the `.aird`. Flat mapping from model element uuid to the artifact
folder(s) bound to it:

```yaml
bdb49505-bc66-4f2c-943e-7a4171f38d2b: "electrical interfaces/Harness-001"
01307778-ae34-4328-aad7-f0c88f0b8cc9: "connectors/Connector-001"
```

A value may be a single folder or a list, so one element can pull in
multiple artifact bundles (e.g. a harness diagram *and* a separate
mechanical drawing for the same link). This file only maps uuid →
folder(s); it says nothing about *what's inside* a folder.

## Per-folder manifest (`artifact.yaml`) — the package

Each artifact folder owns its own manifest, describing its content as an
**ordered list of typed sections** — not a dict of typed keys,
specifically so that section order can be controlled and a type can
repeat (e.g. PDF → 3D model → another PDF):

```yaml
name: Harness-001
description: 4-wire power/CAN harness between two Molex KK 254 connectors.
doc: overview.md       # optional: long-form intro, rendered above the sections
sections:
  - type: wireviz
    path: harness.yaml
    description: Wire colours and pin assignments as built.
  - type: markdown
    path: notes.md
```

```yaml
name: Bracket Assembly
description: Mounting bracket for the antenna deployment mechanism.
sections:
  - type: pdf
    path: overview.pdf
    options:
      pages: "1-3"
  - type: 3dmodel
    path: bracket-v2.glb
    description: As-built revision, superseding the v1 bracket.
    options:
      camera: [0.4, 0.3, 1.2]
      up: z
  - type: pdf
    path: torque-spec.pdf
```

### `description`, `doc`, and a `markdown` section

Three different jobs, so three fields rather than one overloaded one:

- **`description`** — a single plain-text line, always inline in the
  YAML. It is the *label*: what appears in an index listing, a hover, a
  search result, a collapsed section header. Because a consumer may want
  only this one line, getting it must never require opening and parsing
  another file.
- **`doc`** — an optional path to a Markdown file, rendered above the
  content as an introduction. This is where prose of any real length
  goes; writing that inside YAML is miserable, so it doesn't live there.
- **a `markdown` section** — ordinary content, positioned in the section
  order like any other section.

`doc` never overwrites `description`; they layer — `description` as the
lede, `doc` as the body. Both fields exist at the artifact level and
per-section, with the same meanings scoped accordingly: on a section,
`description` is a one-line caption and `doc` is a Markdown intro
rendered immediately before that section's content. A section's `doc` is
prose *about* the section; a `markdown` section is content in its own
right.

### Path resolution and scoping

All paths are relative — never absolute. Beyond that there is no
sandbox, and this is a deliberate decision rather than an oversight:

- Values in `artifacts/index.yaml` are relative to **the index file's own
  directory**, not the model root. That keeps the common entry short
  (`"connectors/Connector-001"`) while still letting an artifact that
  lives outside `artifacts/` be reached — `"../analysis/ANA-001"` binds
  the folder capella-cubed writes, which no root-relative spelling would
  have made shorter.
- Every `path` inside an `artifact.yaml` — sections, `doc`, and anything
  a section type resolves internally (e.g. an image referenced from a
  Markdown file) — is relative to the artifact folder that manifest
  lives in, and **may traverse upward with `../`**. Symlinks are
  followed. A manifest at `imported-repo/pcbs/PCBA/artifact.yaml` can
  reference `../../datasheets/molex-kk254.pdf`, which is the whole point:
  a discipline repo keeps one copy of a shared datasheet, and every
  artifact folder that needs it points at that copy instead of carrying
  a duplicate that goes stale the first time it's revised.

There is no path-based access control here because it would be
protecting nothing. This runs on a closed system, executed by engineers
either locally or against a server they have already authenticated to;
a manifest author who wants to read a file can already read it.

Two limits remain, and neither is a safety measure — both are about a
manifest resolving *identically* for both consumers:

- **Absolute paths are rejected.** They encode one machine's layout and
  break the moment the repo is cloned anywhere else.
- **A path only reaches as far as the consumer can read.** The package
  defines no outer boundary of its own; each consumer hands it a root to
  read within. The CLI's is the checkout it was started in. Model
  Explorer's is the model resource root, because reads there go through
  a handler that cannot escape it — that constraint belongs to the
  consumer, not to this package's rules.

So the guidance is "stay inside your own repository" — offered as the
line between portable and non-portable, not enforced as a boundary.
Upward traversal within the discipline repo resolves identically
everywhere, because the repo's internal structure is the same whether
it's a standalone checkout or a submodule; a path that climbs out of the
repo may work in the CLI and then fail once the consumer's root cuts it
off. A path that can't be resolved is reported like any other broken
section.

### Section options

A section may carry an `options:` mapping, interpreted by that section
type's renderer and by nothing else. Reserved from the start so adding
one later isn't a schema break. Options are always optional; a section
with none must still render sensibly.

| Type | Option | Meaning |
|---|---|---|
| *any* | `max_height` | cap the height of images in the section — a number (px) or a CSS length |
| `wireviz` | `wrap` | `auto` (default), `never`, `always` — see below |
| `wireviz` | `designator` | reference designator for a wrapped template (default `X1`) |
| `wireviz` | `prepend` | file(s) whose text goes in front of the harness before parsing |
| `pdf` | `pages` | page selection, e.g. `"1-3,7"` — render only those pages |
| `pdf` | `height` | viewer height in px (default 720) |
| `3dmodel` | `camera` | direction to view from; the distance is fitted to the model |
| `3dmodel` | `up` | `y` (glTF default) or `z`, for CAD exports that come out rotated |
| `3dmodel` | `height` | viewer height in px (default 480) |
| `html` | `height` | frame height in px for a complete document (default 720) |
| `jupyter` | `cells` | which cells to show, `"6-9"`, same syntax as `pdf`'s `pages` |
| `jupyter` | `tags` | keep only cells carrying one of these tags |
| `jupyter` | `include_source` | show the code as well as its output (default: output only) |

`markdown` and `html` take no options today.

The `wireviz` pair exists because two shapes of source file turn up: a
complete harness, and a bare connector template that only defines a
reusable YAML anchor. WireViz silently drops any connector no connection
set references, so a template rendered alone comes out *empty rather than
failing* — the renderer appends a minimal self-referencing `connections:`
block to prevent that. Which shape a file is gets detected (a complete
harness has `connectors:`) rather than declared, since the file already
says; `wrap` is there for when the guess is wrong.

`prepend` is the same problem from the other end: a harness that
*references* a shared template by anchor is not valid alone either, and
WireViz has no cross-file include, so the template's text must precede
it. That is how one connector definition serves every harness that
terminates in it without any of them carrying a copy.

An unrecognised key inside `options:` is a warning, not an error — the
section still renders with whatever was understood. That keeps a manifest
written against a newer renderer usable on an older one.

`jupyter` ended up needing no `nbformat` dependency: the notebook format
is a documented JSON schema and the renderer reads four keys of it. A
library that exists to *validate* notebooks earns its place in a tool
that writes them, not one that shows them.

### Collapsing and print

Each artifact and each section renders as a `<details>`, open by default.
Collapsed, a section shows one line: its label, its type, and a link to
the file it was rendered from. Every section type carries that link, not
only the ones with a viewer.

The line exists because something has to survive the cases where the
content cannot be shown. A PDF in an iframe and a WebGL canvas both print
blank, so under `@media print` neither is printed and the line is what
appears in its place — a named, linked reference instead of an empty
rectangle. The same line is what a collapsed section shows on screen.

### Missing and malformed content

A page renders as much as it can. One broken section never takes down the
sections around it.

**Non-fatal** — the section is replaced in-place by a visible placeholder
stating what was declared and what went wrong, the same is logged, and
rendering continues with the next section:

- a `path` that doesn't exist, isn't readable, is absolute, or resolves
  somewhere the consumer can't read from (e.g. above the model root)
- an unknown `type` (a manifest using a type this renderer doesn't have)
- content that fails to render (malformed WireViz source, corrupt glTF)

**Fatal for one artifact folder** — there's nothing to enumerate sections
from, so the folder renders as a single error card; other folders bound
to the same element still render normally:

- `artifact.yaml` missing from a folder the index points at
- `artifact.yaml` unparseable, or missing `sections:`

The distinction exists because silence is the failure mode to avoid: an
artifact that was declared and isn't there has to be *visible* on the
page, not merely absent from it.

### Section types (renderer registry)

A fixed, extensible vocabulary — each type maps to one render function.
New types are added by adding one registry entry, never by touching a
page template:

| Type | Renders via | New infra needed? |
|---|---|---|
| `wireviz` | existing WireViz pipeline (self-referencing-wrapper trick for bare connector templates) | No |
| `markdown` | Markdown → HTML | No |
| `html` | a fragment inline; a complete document in an iframe | No |
| `pdf` | an embedded viewer pointed at a served file | Yes — file-serving HTTP route |
| `3dmodel` | Three.js viewer, glTF/GLB only | Yes — same file-serving route |
| `jupyter` | extracted notebook cell outputs | No — plain JSON is enough |

**Phase 1** (no new infrastructure): `index.yaml` + manifest schema +
`wireviz`/`markdown`/`html`.
**Phase 2**: the file-serving route, then `pdf`/`3dmodel`/`jupyter`.

Both phases are now built. The route turned out to be less of a threshold
than expected, because it is the *consumer's* to provide, and `jupyter`
needed no new infrastructure at all — a notebook carries its images
inside its own JSON.

The route turned out to be less of a threshold than expected, because it
is the *consumer's* to provide: the package only asks its file source for
a URL (`url_for`), and a section type that cannot be inlined reports the
consumer having no route the same way it reports a missing file. `pdf` is
therefore already built against the CLI's route, ahead of Model
Explorer's.

## Repository model: per-discipline repos as git submodules — consumer side

Each engineering discipline can own an independent repository (e.g. a
KiCad PCB repo, a 3D-models repo), with its own history, tooling, and CI —
pulled into the MBSE model's repository as a **git submodule**, checked
out at some path under the model root (e.g. `artifacts/pcb-repo/`).

This is compatible with how Model Explorer already reads artifacts: all
reads go through the model's root file handler
(`model.resources["\x00"]`), which is sandboxed to the resource root (no
`../` escape) but doesn't care whether a subdirectory is an ordinary
folder or a checked-out submodule — it's just files on disk either way.
The one real requirement is operational: whatever clones the model for
Model Explorer to read must actually initialize submodules (`git clone
--recurse-submodules`, or an explicit `git submodule update --init`).

## Tooling architecture

The `sections:` rendering logic (manifest parsing + the type→renderer
registry) is factored into a **standalone, installable package**,
independent of `capella-model-explorer` — same relationship this project
already has with `capellambse-context-diagrams` (a separate repo,
installed as a normal dependency, sometimes pinned to a specific
fork/branch).

Two consumers of that shared package:

1. **A local CLI/dev-server**, run directly inside a discipline's own
   repo (e.g. the PCB repo), with no Capella model or uuid resolution
   involved at all — renders any folder under the checkout that has an
   `artifact.yaml`, lists them all on an index, and serves them with
   live-reload. Lets an engineer validate their manifest before ever
   committing it or having it pulled into the MBSE project.
2. **`capella-model-explorer` itself**, once wired in: its own job
   narrows to resolving uuid → folder via `artifacts/index.yaml`, then
   handing that folder to the shared package's renderer and embedding
   the result in the page.

Both consumers resolve a manifest by the same rules, so what renders in
the CLI is what renders in Model Explorer — provided the manifest's paths
stay inside the discipline repo, which is the one case where the two
environments differ (see *Path resolution and scoping*).

### File access is the consumer's, not the package's

The package cannot assume the folder is on a local disk. Model Explorer
reads everything through capellambse's root resource handler, which may
be backed by a git clone or an HTTP endpoint with no local path at all
and no meaningful `..`.

So reading is one small protocol — `read_bytes(path)` and
`exists(path)`, taking root-relative POSIX paths — and each consumer
supplies it. A local implementation ships with the package for the CLI;
Model Explorer wraps its own handler. This is also what makes the
resolution rules above implementable: paths are collapsed *lexically*
into root-relative strings rather than by asking a filesystem, which is
the only form a non-filesystem handler can accept, and it makes climbing
above the root something a manifest structurally cannot express.

## Implementation status

Phase 1 is built, in this repository: manifest parsing, the type→renderer
registry, path resolution, the failure behaviour above, and the
`wireviz`/`markdown`/`html` renderers, plus a `mav` CLI with
`serve`/`render`/`check` and worked examples under `examples/`. See
`README.md`.

`pdf` is built too, ahead of the rest of Phase 2, including `pages`
extraction — the selection travels in the URL and the serving side cuts
the document, so an 8 MB, 34-page specification arrives as the two pages
that were asked for.

So is `3dmodel`, **glTF only**. Rendering STEP would mean tessellating it,
which in Python means OpenCascade — a few hundred megabytes in every
deployment, and minutes of CPU per assembly, to produce a picture a CAD
export gives you for free. The decision is that this view is for
reference (*which* part is being discussed), while the detail lives in the
drawings, schematics and PDFs beside it; CAD inspection happens in CAD.
An engineer exports glTF the way they already export a PDF drawing. Where
STEP is the source of truth, `tools/step_to_glb.py` tessellates it at
build time - in the discipline repo that owns the CAD, beside that repo's
other tooling - and the manifest points at the result. Measured on a
14 MB, 483-part assembly: ten seconds and 2.7 MB of glTF, once, versus
the same ten seconds on every page view.

### Wired into Model Explorer

`capella_model_explorer/artifacts.py` is the consumer half, and it is as
small as the split promised: a `ModelFileSource` over
`model.resources[" "]` (with the `url_for` that `pdf` and `3dmodel`
need), `folders_for()` reading the index, and `render_artifacts()`
handing folders to the renderer and logging what came back. An
`/artifact-file/{path}` route serves what a page then asks the browser to
fetch, honouring `?pages=` for PDFs. `render_artifacts` is registered as
a Jinja global; the physical-link and physical-port templates call it.

Measured against the Munin model: uuid → folder → rendered page, WireViz
SVG and notebook outputs inline, and an 8.0 MB specification served as
164 KB when a section asks for two of its pages.

Left alone: `interfaces.py` still holds the PVMT lookups
(`get_interface_type`, `get_display_label`), which the templates still
use for a label. Its `render_harness_diagram` and
`render_connector_diagram` are now unused by any template, and its
`physical_links`/`physical_ports` index format was already out of step
with the flat index the model actually carries — retiring them is a
follow-up, not something to do while wiring.

## Open decisions

- The package name is a working choice, not a settled one:
  `mbse-artifact-viewer` (module `mbse_artifact_viewer`, CLI `mav`),
  deliberately not "Capella"-branded since discipline teams using it
  standalone don't need to know or care about Capella. Renaming is a
  one-line change in `pyproject.toml` plus a directory move.
- Whether this stays a local scaffold or becomes its own GitHub repo,
  installed the way `capellambse-context-diagrams` already is.
- Whether `Harness-001` should also borrow its connectors from
  `Connector-001` via `prepend:`, the way `Harness-003` now does. It
  still respecifies the same Molex KK 254 pinout inline for X1 and X2,
  which is the duplication the shared template exists to remove.
