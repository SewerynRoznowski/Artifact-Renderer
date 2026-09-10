"""``mav`` - render, serve, or check an artifact folder.

Three verbs, matching the three things an engineer does with a manifest
they are writing: look at it (``serve``), hand it to someone (``render``),
and find out whether it is complete before committing it (``check``).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import typing as t

from .render import render_folder


def find_root(folder: pathlib.Path) -> pathlib.Path:
    """The checkout ``folder`` sits in, as far as ``../`` may climb.

    The nearest ancestor holding a ``.git`` - which is the repository an
    engineer is working in, and the boundary the spec calls the line
    between portable and non-portable. Falling back to the folder itself
    is the conservative answer: no upward traversal at all, rather than
    silently granting the whole filesystem.
    """
    for candidate in [folder, *folder.parents]:
        if (candidate / ".git").exists():
            return candidate
    return folder


def _resolve(args: argparse.Namespace) -> tuple[pathlib.Path, pathlib.Path]:
    folder = pathlib.Path(args.folder).resolve()
    if not folder.is_dir():
        raise SystemExit(f"mav: {folder} is not a directory")
    root = (
        pathlib.Path(args.root).resolve()
        if args.root
        else find_root(folder)
    )
    if root not in [folder, *folder.parents]:
        raise SystemExit(f"mav: {folder} is not inside root {root}")
    return folder, root


def _report(result: t.Any, stream: t.IO[str] = sys.stderr) -> int:
    for diagnostic in result.diagnostics:
        print(f"  {diagnostic}", file=stream)
    return 1 if result.errors else 0


def cmd_render(args: argparse.Namespace) -> int:
    folder, root = _resolve(args)
    result = render_folder(folder, root)
    output = result.html if args.fragment else result.document()

    if args.output:
        path = pathlib.Path(args.output)
        path.write_text(output, encoding="utf-8")
        print(f"  wrote {path}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return _report(result)


def cmd_check(args: argparse.Namespace) -> int:
    folder, root = _resolve(args)
    result = render_folder(folder, root)
    status = _report(result, sys.stdout)
    if result.ok:
        count = len(result.manifest.sections) if result.manifest else 0
        print(f"  {folder.name}: {count} section(s), all rendered")
    return status


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    folder, root = _resolve(args)
    serve(
        folder,
        root,
        host=args.host,
        port=args.port,
        live_reload=not args.no_reload,
        open_browser=not args.no_open,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mav",
        description=(
            "Render an artifact folder described by an artifact.yaml. "
            "Knows nothing about Capella: point it at a folder."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "folder",
            nargs="?",
            default=".",
            help="the artifact folder (default: the current directory)",
        )
        sub.add_argument(
            "--root",
            help=(
                "how far '../' in the manifest may climb "
                "(default: the enclosing git checkout)"
            ),
        )

    render = subcommands.add_parser("render", help="render to HTML")
    add_common(render)
    render.add_argument("-o", "--output", help="write here instead of stdout")
    render.add_argument(
        "--fragment",
        action="store_true",
        help="emit the embeddable fragment, not a standalone page",
    )
    render.set_defaults(func=cmd_render)

    check = subcommands.add_parser(
        "check", help="report anything declared that did not render"
    )
    add_common(check)
    check.set_defaults(func=cmd_check)

    serve = subcommands.add_parser("serve", help="serve with live reload")
    add_common(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument(
        "-p",
        "--port",
        type=int,
        default=None,
        help="default: 8000, or the next free port if it is taken",
    )
    serve.add_argument(
        "--no-reload", action="store_true", help="disable the reload poll"
    )
    serve.add_argument(
        "--no-open",
        action="store_true",
        help="don't open a browser window",
    )
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
