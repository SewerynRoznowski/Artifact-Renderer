A browser cannot draw STEP. It is boundary representation — surfaces
defined by equations — and something has to turn those into triangles
first. That step happens **once, at build time**, not on every page view:

```sh
pip install cascadio
python tools/step_to_glb.py examples/steps/*.step
```

The converted `.glb` files land in `examples/steps/.build/`, beside the
STEP sources they came from, and this manifest points at them. The
sources stay in the repository, so the conversion can be redone at a
different tolerance whenever someone needs a closer look — and the
supplier still gets a `.step`, not a bag of triangles.

## Why not convert on demand

Tessellating an assembly takes seconds to minutes and a few hundred
megabytes of OpenCascade. Putting that in a request handler means every
Model Explorer deployment carries a CAD kernel, and every page view
recomputes a mesh that never changes. The renderer stays a renderer;
the discipline repo that owns the CAD owns the conversion, next to its
other tooling.

## The two things that always go wrong

**Units.** glTF's convention is metres; CAD exports millimetres. cascadio
reads the unit from the STEP header and converts. The M3 nut is the check
on that: it comes out **5.5 × 6.4 × 2.4 mm**, which is DIN 934 to the
tenth — 5.5 across the flats, 6.35 across the corners, 2.4 high. A part
whose dimensions you already know is worth converting first.

**Axis.** STEP is Z-up, glTF is Y-up. Nothing in the conversion rotates
the geometry, because doing that silently would leave the `.glb`
disagreeing with the CAD it came from. Each section below says `up: z`
instead, and the viewer stands the model upright at display time.
