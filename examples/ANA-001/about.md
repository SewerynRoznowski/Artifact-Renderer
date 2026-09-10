An analysis artifact, produced by [capella-cubed](https://github.com/) as
a Jupyter notebook that loads the model, records its assumptions, and
either guarantees or fails a requirement.

It is here because it shows the same analysis four ways, which is the
whole argument for `sections:` being an ordered list of typed entries
rather than one blob:

- the **generated report**, which is the deliverable — verdict,
  provenance and traceability score in one place;
- the **results**, for a reviewer who wants the conclusion;
- the **working**, code and all, for a reviewer who doubts it;
- **nbconvert's export**, for anyone who would rather read it exactly as
  Jupyter renders it.

The report and the executed notebook live in `.build/`, because they are
generated rather than written. A manifest can point into a dot-directory
like any other folder.

The notebook carries its own images — the context diagram is SVG, the
score plot is a PNG, both base64-encoded inside the `.ipynb`. So a
`jupyter` section needs no second file and no file-serving route, unlike
`pdf` and `3dmodel`.

`analysis_result.json` sits alongside, holding the machine-readable
verdict (status, provenance hashes, the git commit the run came from).
Nothing renders it yet; it is here because a real analysis folder has one.
