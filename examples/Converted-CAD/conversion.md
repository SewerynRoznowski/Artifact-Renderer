## What each conversion cost

Measured on the three STEP files in `examples/steps/`:

| Part | STEP | glTF | Time | Parts | Triangles | Tolerance |
|---|---|---|---|---|---|---|
| DIN 934 M3 nut | 25 KB | 21 KB | 0.4 s | 1 | 648 | 0.05 mm |
| bauform1 | 667 KB | 510 KB | 0.6 s | 5 | 17,160 | 0.1 mm |
| PROC048A | 14.0 MB | 2.7 MB | 9.8 s | 483 | 73,394 | 0.2 mm |

The 14 MB assembly is the one that makes the argument. Ten seconds is
nothing once, at build time; it is unacceptable on every page view, and
the mesh it produces is identical every time.

## Choosing a tolerance

`--tol-linear` is the largest distance a triangle may sit from the true
surface, in millimetres. It is the size/fidelity dial, and it moves the
output by an order of magnitude:

- **0.01–0.05 mm** — a small machined part, or anything with a thread or
  fillet whose shape is the point.
- **0.1 mm** — a housing or bracket. Curves still read as curves.
- **0.2–0.5 mm** — a large assembly nobody will measure on screen. This
  is what keeps PROC048A at 2.7 MB rather than tens of megabytes.

Too fine and the file is slow to load for no visible gain. Too coarse and
a cylinder becomes a visible polygon. Convert, look at it, adjust — the
STEP is still there.

## What is lost

Tessellation is one-way. The `.glb` has no parametric history, no exact
surfaces, no dimensions or tolerances, no PMI. That is not a shortcoming
of the pipeline; it is what makes it the right pipeline. This view exists
so a reviewer can see **which** part is being discussed. The numbers that
have to be met live in the drawing and the specification beside it, and
anyone who needs the geometry itself takes the STEP.
