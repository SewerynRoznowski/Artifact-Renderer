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
import urllib.parse


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

    # Optional. A source may also implement:
    #
    #     def url_for(self, path, params=None) -> str
    #
    # returning a URL the *browser* can fetch that file from. Some
    # content cannot be inlined into the page - a browser will not open a
    # PDF handed to it as a data: URI - so those section types need a real
    # file-serving route, and only the consumer knows its URL space. A
    # source without this method simply cannot render those types; they
    # report that rather than half-working.


def url_for(
    source: FileSource,
    path: str,
    params: t.Mapping[str, str] | None = None,
) -> str | None:
    """A browser-fetchable URL for ``path``, if this source offers one."""
    builder = getattr(source, "url_for", None)
    if builder is None:
        return None
    return builder(path, params)


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

    def url_for(
        self, path: str, params: t.Mapping[str, str] | None = None
    ) -> str:
        """The URL the dev server serves this file at.

        Root-relative, matching the server's static route, so the two
        agree by construction. Each segment is quoted separately to keep
        the slashes - and because real datasheet filenames are full of
        ``+`` and spaces.
        """
        url = "/" + "/".join(
            urllib.parse.quote(part) for part in path.split("/") if part
        )
        if params:
            url += "?" + urllib.parse.urlencode(dict(params))
        return url

    def __repr__(self) -> str:
        return f"LocalFileSource({str(self.root)!r})"


def read_text(source: FileSource, path: str) -> str:
    """Read ``path`` as UTF-8, tolerating a stray byte.

    Engineering source files get edited by a lot of different tools;
    ``errors="replace"`` means one mis-encoded degree sign in a comment
    doesn't take out an otherwise fine harness diagram.
    """
    return source.read_bytes(path).decode("utf-8", errors="replace")
