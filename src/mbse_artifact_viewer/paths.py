"""Path resolution.

Per the spec: manifest paths are relative, never absolute, and may
traverse upward with ``../`` - a manifest at
``imported-repo/pcbs/PCBA/artifact.yaml`` referencing
``../../datasheets/molex-kk254.pdf`` is the motivating case, not an abuse
to be blocked. There is no access control here; it would be protecting
nothing on a closed system where the manifest's author can already read
whatever they point at.

Two properties are worth being careful about anyway, and both are about a
manifest resolving *identically* wherever it's rendered:

**Resolution is lexical, not filesystem-based.** ``..`` is collapsed by
manipulating path segments, without asking the filesystem to resolve
anything. That is what lets a consumer back this with something that
isn't a filesystem at all - Model Explorer reads through capellambse's
resource handler, where a git- or HTTP-backed model has no local path and
no meaningful ``..``. Every path this module produces is a plain
root-relative POSIX string, which such a handler can take directly.

**The root is the consumer's, not ours.** Because a path is expressed
relative to the root, climbing above it is not something a manifest can
express - the attempt is reported like any other broken section. This
package never picks the root: the CLI passes the checkout it was started
in, Model Explorer passes the model's resource root.
"""

from __future__ import annotations

import pathlib

from .errors import PathError


def normalize_folder(folder: str) -> str:
    """Normalize a root-relative folder path (``""`` being the root)."""
    return join_relative("", folder) if folder else ""


def join_relative(folder: str, raw: str) -> str:
    """Resolve ``raw``, declared inside ``folder``, to a root-relative path.

    ``folder`` is itself root-relative POSIX (``""`` for the root).
    ``raw`` is a path as written in a manifest. Backslashes are accepted
    and normalized, since a Windows engineer will occasionally type one,
    but forward slashes are the portable spelling.

    Raises :class:`PathError` for the three unusable cases: empty,
    absolute, or resolving above the root.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise PathError("path is empty")

    text = raw.strip().replace("\\", "/")
    _reject_absolute(text)

    parts: list[str] = [p for p in folder.split("/") if p and p != "."]
    for part in text.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                raise PathError(
                    f"{raw!r} resolves above the root this consumer can "
                    "read within"
                )
            parts.pop()
            continue
        parts.append(part)

    if not parts:
        raise PathError(f"{raw!r} resolves to the root itself, not a file")
    return "/".join(parts)


def _reject_absolute(text: str) -> None:
    """Reject absolute paths, in either platform's spelling.

    Worth spelling out because the obvious check is wrong on Windows:
    ``pathlib.Path("/etc/passwd").is_absolute()`` is *False* there, since
    the path has no drive. Both flavours are checked explicitly so a
    manifest behaves the same on either platform.
    """
    if (
        pathlib.PurePosixPath(text).is_absolute()
        or pathlib.PureWindowsPath(text).is_absolute()
        or pathlib.PureWindowsPath(text).drive
    ):
        raise PathError(
            f"{text!r} is an absolute path; it encodes one machine's "
            "layout and breaks on any other checkout"
        )


def parent_of(path: str) -> str:
    """The root-relative folder containing ``path`` (``""`` at the root)."""
    head, _, _ = path.rpartition("/")
    return head
