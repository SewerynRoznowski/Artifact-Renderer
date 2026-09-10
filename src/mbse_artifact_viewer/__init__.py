"""Render an engineering artifact folder described by an ``artifact.yaml``.

The package's whole world is a folder containing an ``artifact.yaml``. It
never sees a uuid, an ``.aird``, a PVMT property or a ``capellambse``
object - a discipline team rendering their own PCB repo locally has no
Capella model to hand and shouldn't need one. Resolving *which* folder
belongs to which model element is the consumer's job.

Typical use, standalone::

    from mbse_artifact_viewer import render_folder
    print(render_folder("artifacts/Harness-001").document())

Typical use from a consumer that reads through its own file handler::

    from mbse_artifact_viewer import render_artifact
    result = render_artifact(my_source, "artifacts/Harness-001")
    embed(result.html)
    for diagnostic in result.diagnostics:
        logger.warning("%s", diagnostic)
"""

from __future__ import annotations

from .errors import ArtifactError, Diagnostic, Level, PathError, SectionError
from .manifest import MANIFEST_NAME, Manifest, Section
from .manifest import load as load_manifest
from .registry import RenderContext, known_types, renderer
from .render import (
    EMBED_STYLESHEET,
    PAGE_STYLESHEET,
    STYLESHEET,
    RenderResult,
    render_artifact,
    render_folder,
)
from .sources import FileSource, LocalFileSource

__version__ = "0.1.0"

__all__ = [
    "EMBED_STYLESHEET",
    "MANIFEST_NAME",
    "PAGE_STYLESHEET",
    "STYLESHEET",
    "ArtifactError",
    "Diagnostic",
    "FileSource",
    "Level",
    "LocalFileSource",
    "Manifest",
    "PathError",
    "RenderContext",
    "RenderResult",
    "Section",
    "SectionError",
    "__version__",
    "known_types",
    "load_manifest",
    "render_artifact",
    "render_folder",
    "renderer",
]
