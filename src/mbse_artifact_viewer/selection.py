"""Parsing ``"1-3,7"`` - a selection of numbered things.

Shared, because two section types need the same syntax for the same
reason: ``pdf`` selecting pages and ``jupyter`` selecting cells. An
engineer who has learned one shouldn't have to learn the other.

One-based throughout, because that is how a person counts the pages of a
document and the cells of a notebook.
"""

from __future__ import annotations

import re

_RANGE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


def parse(spec: object, what: str = "page") -> list[int]:
    """Parse ``"1-3,7"`` into ``[1, 2, 3, 7]`` (ordered, unique).

    Accepts a bare int and a list of ints too, since YAML hands over
    ``pages: 3`` and ``pages: [1, 5]`` as those types.
    """
    if isinstance(spec, bool):  # bool is an int; "pages: yes" is nonsense
        raise ValueError(f"{spec!r} is not a {what} selection")
    if isinstance(spec, int):
        parts = [str(spec)]
    elif isinstance(spec, (list, tuple)):
        parts = [str(part) for part in spec]
    elif isinstance(spec, str):
        parts = spec.split(",")
    else:
        raise ValueError(f"{spec!r} is not a {what} selection")

    numbers: list[int] = []
    for part in parts:
        match = _RANGE.match(part)
        if not match:
            raise ValueError(
                f"{part.strip()!r} is not a {what} or {what} range "
                '(try "3", "1-4", or "1-2,7")'
            )
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1:
            raise ValueError(f"{what} numbers start at 1")
        if last < first:
            raise ValueError(f"{what} range {first}-{last} runs backwards")
        numbers.extend(range(first, last + 1))

    ordered = sorted(set(numbers))
    if not ordered:
        raise ValueError(f"no {what}s selected")
    return ordered


def format(numbers: list[int]) -> str:  # noqa: A001 - it is a formatter
    """The inverse of :func:`parse`, collapsing runs."""
    parts: list[str] = []
    for number in numbers:
        if parts:
            first, _, last = parts[-1].partition("-")
            if number == int(last or first) + 1:
                parts[-1] = f"{first}-{number}"
                continue
        parts.append(str(number))
    return ",".join(parts)


def describe(numbers: list[int], what: str = "page") -> str:
    """A human phrasing of a selection, for a caption."""
    if len(numbers) == 1:
        return f"{what} {numbers[0]}"
    return f"{what}s {format(numbers).replace('-', '–')}"
