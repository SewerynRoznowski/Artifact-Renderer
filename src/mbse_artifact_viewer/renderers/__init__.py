"""Built-in section renderers.

Importing this package is what puts the Phase 1 types in the registry.
Adding a type means adding a module here and one line below - the page
template never learns about it.
"""

from . import html_, markdown_, pdf_, wireviz_

__all__ = ["html_", "markdown_", "pdf_", "wireviz_"]
