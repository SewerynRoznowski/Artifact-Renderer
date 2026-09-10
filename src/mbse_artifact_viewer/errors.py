"""Failure vocabulary.

The spec's central rule is that silence is the failure mode to avoid: an
artifact that was declared and isn't there has to be *visible* on the
page, not merely absent from it. That splits every failure in two.

:class:`ArtifactError` is fatal for one folder - there is nothing to
enumerate sections from, so the folder renders as a single error card.

:class:`SectionError` is not fatal for anything: the one section is
replaced in-place by a placeholder saying what was declared and what went
wrong, and rendering continues with the next section.

Both are also collected as :class:`Diagnostic` records, so a consumer
(the CLI's exit code, Model Explorer's log) can see what went wrong
without scraping the HTML.
"""

from __future__ import annotations

import dataclasses
import enum


class ArtifactError(Exception):
    """Fatal for one artifact folder: no sections can be enumerated."""


class SectionError(Exception):
    """Non-fatal: this one section cannot be rendered."""


class PathError(SectionError):
    """A manifest path is unusable - absolute, empty, or above the root."""


class Level(enum.StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class Diagnostic:
    """One thing that went wrong, in a form a consumer can log."""

    level: Level
    message: str
    #: Root-relative folder of the artifact this came from.
    folder: str = ""
    #: Position in ``sections:``, or ``None`` for artifact-level problems.
    section: int | None = None
    #: The section's declared ``type``, when there was one.
    type: str | None = None

    def __str__(self) -> str:
        where = self.folder or "<artifact>"
        if self.section is not None:
            where = f"{where} section {self.section}"
            if self.type:
                where = f"{where} ({self.type})"
        return f"{self.level}: {where}: {self.message}"
