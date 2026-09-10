"""Parsing ``artifact.yaml``.

The manifest describes a folder's content as an *ordered list of typed
sections* - not a dict of typed keys - so that order is controllable and
a type can repeat (PDF, then a 3D model, then another PDF).

Parsing is deliberately lenient about everything except the one thing it
cannot recover from: if there is no readable ``sections:`` list, there is
nothing to render and the folder is fatal. Anything else - a section
that isn't a mapping, a missing ``type``, a key nobody recognises -
becomes a diagnostic and, where it belongs to one section, a placeholder
in that section's slot.
"""

from __future__ import annotations

import dataclasses
import typing as t

import yaml

from .errors import ArtifactError, Diagnostic, Level
from .paths import normalize_folder
from .sources import FileSource, read_text

MANIFEST_NAME = "artifact.yaml"

_ARTIFACT_KEYS = frozenset({"name", "description", "doc", "sections"})
_SECTION_KEYS = frozenset({"type", "path", "description", "doc", "options"})


@dataclasses.dataclass(frozen=True)
class Section:
    """One entry of ``sections:``."""

    index: int
    type: str
    path: str | None = None
    description: str | None = None
    doc: str | None = None
    options: dict[str, t.Any] = dataclasses.field(default_factory=dict)
    #: Set when the entry was too malformed to describe a renderable
    #: section; :mod:`.render` turns it straight into a placeholder.
    error: str | None = None


@dataclasses.dataclass(frozen=True)
class Manifest:
    """A parsed ``artifact.yaml``."""

    #: Root-relative folder this manifest lives in.
    folder: str
    name: str
    description: str | None
    doc: str | None
    sections: list[Section]


def load(source: FileSource, folder: str) -> tuple[Manifest, list[Diagnostic]]:
    """Load the manifest in ``folder``.

    Raises :class:`ArtifactError` when the folder has nothing renderable
    in it at all - the caller turns that into a single error card, and
    other folders bound to the same element still render.
    """
    folder = normalize_folder(folder)
    path = f"{folder}/{MANIFEST_NAME}" if folder else MANIFEST_NAME

    try:
        text = read_text(source, path)
    except FileNotFoundError:
        raise ArtifactError(f"no {MANIFEST_NAME} in {folder or '.'!r}") from None
    except OSError as err:
        raise ArtifactError(f"cannot read {path}: {err}") from None

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise ArtifactError(f"{path} is not valid YAML: {err}") from None

    if data is None:
        raise ArtifactError(f"{path} is empty")
    if not isinstance(data, dict):
        raise ArtifactError(
            f"{path} must be a mapping, not {type(data).__name__}"
        )
    if "sections" not in data:
        raise ArtifactError(f"{path} has no 'sections:' list")

    raw_sections = data["sections"]
    if not isinstance(raw_sections, list):
        raise ArtifactError(
            f"{path}: 'sections:' must be a list, not "
            f"{type(raw_sections).__name__}"
        )

    diagnostics: list[Diagnostic] = []

    def warn(message: str, section: int | None = None) -> None:
        diagnostics.append(
            Diagnostic(Level.WARNING, message, folder=folder, section=section)
        )

    for key in sorted(set(data) - _ARTIFACT_KEYS):
        warn(f"unrecognised key {key!r} in {MANIFEST_NAME}, ignored")

    name = _as_text(data.get("name")) or folder.rpartition("/")[2] or "Artifact"
    sections = [
        _parse_section(index, entry, warn)
        for index, entry in enumerate(raw_sections)
    ]
    if not sections:
        warn("'sections:' is empty, nothing to render")

    return (
        Manifest(
            folder=folder,
            name=name,
            description=_as_text(data.get("description")),
            doc=_as_text(data.get("doc")),
            sections=sections,
        ),
        diagnostics,
    )


def _parse_section(
    index: int,
    entry: t.Any,
    warn: t.Callable[[str, int | None], None],
) -> Section:
    if not isinstance(entry, dict):
        return Section(
            index=index,
            type="",
            error=(
                "this entry is a "
                f"{type(entry).__name__}, but every section must be a "
                "mapping with at least a 'type'"
            ),
        )

    for key in sorted(set(entry) - _SECTION_KEYS):
        warn(f"unrecognised key {key!r} in section, ignored", index)

    section_type = _as_text(entry.get("type")) or ""
    if not section_type:
        return Section(
            index=index, type="", error="section has no 'type'"
        )

    options = entry.get("options")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        warn(
            f"'options:' must be a mapping, not {type(options).__name__}; "
            "ignored",
            index,
        )
        options = {}

    return Section(
        index=index,
        type=section_type,
        path=_as_text(entry.get("path")),
        description=_as_text(entry.get("description")),
        doc=_as_text(entry.get("doc")),
        options=options,
    )


def _as_text(value: t.Any) -> str | None:
    """Coerce a scalar YAML value to stripped text, or ``None``."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None
