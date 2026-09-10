"""Where files are read from.

The package's world is a folder containing an ``artifact.yaml``; it does
not get to assume that folder is on a local disk. Model Explorer reads
everything through capellambse's own root resource handler
(``model.resources["\\x00"]``), which may be backed by a git clone or an
HTTP endpoint with no local path at all.

So file access is one small protocol, and each consumer supplies it. The
package asks for root-relative POSIX paths and nothing else; whatever
"the root" means is the consumer's business.
"""

from __future__ import annotations

import pathlib
import typing as t


class FileSource(t.Protocol):
    """Read-only access to files under some consumer-defined root."""

    def read_bytes(self, path: str) -> bytes:
        """Read ``path`` (root-relative POSIX).

        Raises :class:`FileNotFoundError` if it isn't there.
        """
        ...

    def exists(self, path: str) -> bool:
        """Whether ``path`` (root-relative POSIX) can be read."""
        ...


class LocalFileSource:
    """A :class:`FileSource` over a local directory.

    Symlinks are followed without inspecting where they point, which is
    the decision the spec records: on a closed system, a symlink out of
    the tree grants no access its author didn't already have.
    """

    def __init__(self, root: pathlib.Path | str) -> None:
        self.root = pathlib.Path(root)

    def _full(self, path: str) -> pathlib.Path:
        return self.root.joinpath(*[p for p in path.split("/") if p])

    def read_bytes(self, path: str) -> bytes:
        return self._full(path).read_bytes()

    def exists(self, path: str) -> bool:
        return self._full(path).exists()

    def __repr__(self) -> str:
        return f"LocalFileSource({str(self.root)!r})"


def read_text(source: FileSource, path: str) -> str:
    """Read ``path`` as UTF-8, tolerating a stray byte.

    Engineering source files get edited by a lot of different tools;
    ``errors="replace"`` means one mis-encoded degree sign in a comment
    doesn't take out an otherwise fine harness diagram.
    """
    return source.read_bytes(path).decode("utf-8", errors="replace")
