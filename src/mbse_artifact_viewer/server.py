"""The local dev server.

The point of this, per the spec, is that an engineer can validate a
manifest inside their own repo *before* committing it or having it pulled
into the MBSE project - no Capella model, no Model Explorer, no uuid.

Deliberately stdlib-only. A package that gets embedded in someone else's
web application should not drag a second web framework in with it.

Two things beyond serving the page:

**Live reload.** The page re-renders on every request and a small poll
loop reloads it when anything under the artifact folder changes, so
editing ``harness.yaml`` in one window updates the diagram in the other.

**Plain files.** Anything that isn't the page is served from the root.
That is what makes ``![](photo.png)`` inside a Markdown section work, and
it is the same route Phase 2's ``pdf`` and ``3dmodel`` types will need.

The page is served at the artifact folder's own position under the root
(``/pcbs/PCBA/``), not at ``/``. That looks like a detail and isn't: a
relative link written inside a Markdown file is resolved by the *browser*,
against the page's URL, and it has to land on the same file the same path
would reach from the manifest. Serving the page at ``/`` would make
``../datasheets/part.png`` mean two different things depending on whether
the manifest or the Markdown file said it.
"""

from __future__ import annotations

import html
import http.server
import mimetypes
import os
import pathlib
import socketserver
import typing as t
import urllib.parse
import webbrowser

from . import pdfpages
from .manifest import MANIFEST_NAME
from .render import STYLESHEET, render_folder

RELOAD_PATH = "/__mav/fingerprint"
_HTML = "text/html; charset=utf-8"

#: Directories never walked when *listing* artifacts - a listing is a
#: menu, and these hold no artifact anyone chose to publish. Serving is a
#: separate decision: a file inside one of these is still served if a
#: manifest asks for it by name.
_SKIP_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__"})

_RELOAD_SCRIPT = f"""
<script>
(function () {{
  let current = null;
  const url = "{RELOAD_PATH}?page=" + encodeURIComponent(location.pathname);
  setInterval(async function () {{
    try {{
      const response = await fetch(url, {{cache: "no-store"}});
      const next = await response.text();
      if (current === null) current = next;
      else if (next !== current) location.reload();
    }} catch (err) {{ /* server restarting; try again next tick */ }}
  }}, 1000);
}})();
</script>
"""

# Not in the stdlib's table on every platform, and Phase 2 will want them.
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("image/svg+xml", ".svg")


def page_url(folder: pathlib.Path, root: pathlib.Path) -> str:
    """Where the page is served, so browser-relative links line up."""
    relative = folder.resolve().relative_to(root.resolve()).as_posix()
    return "/" if relative == "." else f"/{relative}/"


#: Refused by name rather than by leading dot. A dot-directory is
#: ordinary content - capella-cubed writes its generated report into
#: ``.build/`` - and dropping every one of them silently rewrote such a
#: path into a different file. This is the one that is never content.
_NEVER_SERVED = frozenset({".git"})


def _segments(url_path: str) -> list[str]:
    """URL path to path segments.

    ``.`` and ``..`` are dropped rather than resolved: neither has
    anything to mean in a URL here, and dropping them means a path cannot
    climb out of the root by asking.
    """
    return [
        part
        for part in url_path.strip("/").split("/")
        if part and part not in (".", "..")
    ]


def find_artifacts(root: pathlib.Path) -> list[pathlib.Path]:
    """Every folder under ``root`` holding an ``artifact.yaml``."""
    found: list[pathlib.Path] = []
    for manifest in root.rglob(MANIFEST_NAME):
        relative = manifest.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in relative):
            continue
        found.append(manifest.parent)
    return sorted(found)


def fingerprint(folder: pathlib.Path) -> str:
    """A cheap summary of everything under ``folder``.

    Only the artifact folder is watched, not the whole root - a file
    pulled in from a shared ``../datasheets/`` won't trigger a reload on
    its own. Watching an entire repository to catch that would cost more
    than pressing F5.
    """
    stamps: list[str] = []
    for path in sorted(folder.rglob("*")):
        try:
            stat = path.stat()
        except OSError:
            continue
        stamps.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")
    return str(hash("\n".join(stamps)))


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "mbse-artifact-viewer"
    folder: pathlib.Path
    root: pathlib.Path
    page_path: str
    live_reload: bool

    def do_GET(self) -> None:  # noqa: N802 - stdlib's spelling
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == RELOAD_PATH:
            page = urllib.parse.parse_qs(parsed.query).get("page", ["/"])[0]
            watched = self._artifact_at(page) or self.folder
            self._send(fingerprint(watched).encode(), "text/plain")
            return

        if path == "/index.html":
            path = "/"

        # Every directory answers, one way or the other: one holding an
        # artifact.yaml renders as a page, any other lists the artifacts
        # beneath it. Only the folder the server was launched with used to
        # be a page, which left `mav serve` at the root of a repository -
        # the most natural way to run it - falling through to the
        # static-file branch and 404ing on its own front page.
        segments = _segments(path)
        folder = self.root.joinpath(*segments)
        if folder.is_dir() and not (_NEVER_SERVED & set(segments)):
            if not path.endswith("/"):
                # Without the trailing slash the browser resolves every
                # relative link one level too high.
                self._redirect(path + "/")
                return
            body = (
                self._page(folder)
                if (folder / MANIFEST_NAME).is_file()
                else self._index(folder)
            )
            self._send(body.encode("utf-8"), _HTML)
            return

        self._send_file(path, parsed.query)

    def _artifact_at(self, url_path: str) -> pathlib.Path | None:
        """The artifact folder ``url_path`` names, if it is one."""
        candidate = self.root.joinpath(*_segments(url_path))
        if (candidate / "artifact.yaml").is_file():
            return candidate
        return None

    def _page(self, folder: pathlib.Path) -> str:
        result = render_folder(folder, self.root)
        for diagnostic in result.diagnostics:
            self.log_message("%s", diagnostic)
        document = result.document()
        if not (self.root / MANIFEST_NAME).is_file():
            # There is an index to go back to unless the root is itself a
            # single artifact folder.
            document = document.replace(
                '<article class="mav">',
                '<article class="mav">\n<p class="mav-caption">'
                '<a href="/">← all artifacts</a></p>',
                1,
            )
        if self.live_reload:
            document = document.replace("</body>", f"{_RELOAD_SCRIPT}</body>")
        return document

    def _index(self, under: pathlib.Path | None = None) -> str:
        """The artifacts beneath ``under`` (the root by default)."""
        under = under or self.root
        rows = []
        for folder in find_artifacts(under):
            url = page_url(folder, self.root)
            result = render_folder(folder, self.root)
            name = result.manifest.name if result.manifest else folder.name
            description = (
                result.manifest.description if result.manifest else None
            ) or ""
            broken = (
                f' <span class="mav-problem-detail">'
                f"({len(result.errors)} problem"
                f"{'s' if len(result.errors) != 1 else ''})</span>"
                if result.errors
                else ""
            )
            rows.append(
                f'<li><a href="{html.escape(url)}">{html.escape(name)}</a>'
                f"{broken}<br>"
                f'<span class="mav-caption">{html.escape(description)}</span>'
                "</li>"
            )

        body = (
            "<ul>\n" + "\n".join(rows) + "\n</ul>"
            if rows
            else '<p class="mav-caption">No artifact.yaml found under '
            f"this directory.</p>"
        )
        return (
            "<!doctype html>\n<html lang=\"en\">\n<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,'
            'initial-scale=1">\n<title>Artifacts</title>\n'
            "<style>\nbody { margin: 0; padding: 2rem 1.5rem; }\n"
            ".mav ul { list-style: none; padding: 0; }\n"
            ".mav li { border-top: 1px solid var(--mav-line); "
            "padding: .7rem 0; }\n"
            f"{STYLESHEET}</style>\n</head>\n<body>\n"
            '<article class="mav">\n<header class="mav-head">\n'
            f"<h1>Artifacts</h1>\n<p class=\"mav-lede\">"
            f"{html.escape(str(under))}</p>\n</header>\n"
            f"{body}\n</article>\n</body>\n</html>\n"
        )

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _send_file(self, path: str, query: str = "") -> None:
        relative = _segments(path)
        if not relative:
            self.send_error(404)
            return
        if _NEVER_SERVED & set(relative):
            self.send_error(404, f"No such file: {path}")
            return

        candidate = self.root.joinpath(*relative)
        if not candidate.is_file():
            self.send_error(404, f"No such file: {path}")
            return

        body = candidate.read_bytes()
        kind, _ = mimetypes.guess_type(candidate.name)
        pages = urllib.parse.parse_qs(query).get("pages", [None])[0]
        if pages and candidate.suffix.lower() == ".pdf":
            body = self._trim_pdf(body, pages, candidate.name)
        self._send(body, kind or "application/octet-stream")

    def _trim_pdf(self, body: bytes, spec: str, name: str) -> bytes:
        """Serve only the requested pages.

        The extraction belongs here rather than in the renderer because a
        browser will not open a PDF given to it as a ``data:`` URI - it
        needs a URL, so whatever answers that URL is what has to do the
        cutting. Failing over to the whole document keeps a page-selection
        problem from turning into a blank frame.
        """
        try:
            return pdfpages.extract(body, pdfpages.parse_selection(spec))
        except pdfpages.PdfUnavailable as err:
            self.log_message("%s: serving %s in full", err, name)
        except Exception as err:
            self.log_message(
                "could not take pages %s of %s (%s); serving it in full",
                spec,
                name,
                err,
            )
        return body

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: t.Any) -> None:
        print(f"  {format % args}")


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True

    # SO_REUSEADDR does not mean on Windows what it means everywhere else.
    # There it lets a second server bind a port another process is already
    # listening on; the two then split incoming connections between them,
    # so a stale `mav serve` you thought you had stopped answers half your
    # requests with the old page. Better to fail the bind and let the port
    # search move to the next one.
    allow_reuse_address = os.name != "nt"


DEFAULT_PORT = 8000

#: How many ports past the default to try before giving up. A port can be
#: unavailable without being *in use*: Windows reserves whole ranges for
#: Hyper-V and WSL, and a reserved port refuses the bind outright
#: (WinError 10013). Nobody running this wants to debug that - they want
#: to look at their harness - so an unasked-for port just moves along.
_PORT_ATTEMPTS = 20


def open_in_browser(url: str) -> bool:
    """Open ``url`` in the default browser. Never fails the server.

    A machine with no browser configured - a headless box, a container,
    an SSH session - is a perfectly good place to run this and read the
    URL yourself, so not opening anything is a normal outcome rather than
    an error.
    """
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def serve(
    folder: pathlib.Path,
    root: pathlib.Path | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
    live_reload: bool = True,
    open_browser: bool = True,
) -> None:
    """Serve ``folder`` until interrupted.

    ``port=None`` means "pick something that works", starting at
    :data:`DEFAULT_PORT`. An explicitly requested port is never silently
    swapped - if you asked for 8080 and got 8081, the URL you already had
    open in a browser would be quietly wrong.
    """
    root = (root or folder).resolve()
    folder = folder.resolve()
    page_path = page_url(folder, root)

    handler = type(
        "_BoundHandler",
        (_Handler,),
        {
            "folder": folder,
            "root": root,
            "page_path": page_path,
            "live_reload": live_reload,
        },
    )

    httpd, bound = _bind(host, port, handler)
    with httpd:
        others = len(find_artifacts(root)) - 1
        url = f"http://{host}:{bound}{page_path}"
        print(f"  serving {folder}")
        print(f"  root    {root}")
        if page_path != "/" and others > 0:
            print(
                f"  http://{host}:{bound}/  ({others} other artifact"
                f"{'s' if others != 1 else ''} under the root)"
            )
        # flush: stdout block-buffers when piped, and the URL is the
        # one line the user is waiting on.
        print(f"  {url}  (ctrl-c to stop)", flush=True)

        # The socket is already listening by now - server_activate() runs
        # in the constructor - so a browser that gets there first waits in
        # the backlog rather than being refused.
        if open_browser and not open_in_browser(url):
            print("  (could not open a browser; the URL above is it)")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped")


def _bind(
    host: str, port: int | None, handler: type
) -> tuple[_Server, int]:
    """Bind the first usable port, or explain why there wasn't one."""
    wanted = DEFAULT_PORT if port is None else port
    candidates = (
        range(wanted, wanted + _PORT_ATTEMPTS) if port is None else [wanted]
    )

    last: OSError | None = None
    for candidate in candidates:
        try:
            return _Server((host, candidate), handler), candidate
        except OSError as err:
            last = err

    raise SystemExit(_why(host, wanted, port is None, last))


def _why(
    host: str, wanted: int, searched: bool, err: OSError | None
) -> str:
    tried = (
        f"ports {wanted}-{wanted + _PORT_ATTEMPTS - 1}"
        if searched
        else f"port {wanted}"
    )
    lines = [f"mav: cannot serve on {host}: {tried} unavailable ({err})"]
    if getattr(err, "winerror", None) == 10013:
        lines += [
            "",
            "  Windows refuses the bind when a port is reserved, which",
            "  Hyper-V and WSL do in whole blocks. Reserved ranges:",
            "    netsh interface ipv4 show excludedportrange protocol=tcp",
        ]
    lines.append("  Pick another with: mav serve <folder> -p 8931")
    return "\n".join(lines)
