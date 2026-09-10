from __future__ import annotations

import json

from mbse_artifact_viewer import render_folder

#: A traceback as Jupyter saves it, colour codes and all.
TRACEBACK = "[31mValueError[0m: boom"

NOTEBOOK = {
    "nbformat": 4,
    "cells": [
        {"cell_type": "markdown", "source": ["# Heading\n"]},
        {
            "cell_type": "code",
            "source": ["plot()\n"],
            "metadata": {"tags": ["report"]},
            "outputs": [
                {
                    "output_type": "execute_result",
                    "data": {
                        "image/svg+xml": "<svg id='diagram'></svg>",
                        "text/plain": "<Figure>",
                    },
                }
            ],
        },
        {
            "cell_type": "code",
            "source": ["print('hello')\n"],
            "outputs": [
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": ["hello\n"],
                }
            ],
        },
        {
            "cell_type": "code",
            "source": ["boom()\n"],
            "outputs": [
                {
                    "output_type": "error",
                    "evalue": "boom",
                    "traceback": [TRACEBACK],
                }
            ],
        },
    ],
}


def render(tmp_path, options="", notebook=None):
    (tmp_path / "nb.ipynb").write_text(
        json.dumps(notebook if notebook is not None else NOTEBOOK),
        encoding="utf-8",
    )
    (tmp_path / "artifact.yaml").write_text(
        "name: x\nsections:\n  - type: jupyter\n    path: nb.ipynb\n" + options,
        encoding="utf-8",
    )
    return render_folder(tmp_path)


def test_shows_prose_and_outputs_but_not_code(tmp_path):
    """An analysis notebook is a working document; the results are the
    part a reviewer wants."""
    result = render(tmp_path)

    assert "<h1>Heading</h1>" in result.html
    assert "<svg id='diagram'></svg>" in result.html
    assert "hello" in result.html
    assert "plot()" not in result.html, "source is hidden by default"


def test_include_source_brings_the_code_back(tmp_path):
    result = render(tmp_path, "    options:\n      include_source: true\n")
    assert "plot()" in result.html
    assert "mav-nb-source" in result.html


def test_the_richest_output_wins(tmp_path):
    """SVG over the text/plain fallback that always accompanies it."""
    result = render(tmp_path)
    assert "<svg" in result.html
    assert "&lt;Figure&gt;" not in result.html


def test_a_traceback_keeps_its_text_and_loses_its_colour_codes(tmp_path):
    result = render(tmp_path)
    assert "ValueError: boom" in result.html
    assert "" not in result.html
    assert "mav-nb-err" in result.html


def test_cells_selects_by_position(tmp_path):
    result = render(tmp_path, "    options:\n      cells: '1'\n")
    assert "<h1>Heading</h1>" in result.html
    assert "hello" not in result.html


def test_tags_select_by_label(tmp_path):
    result = render(tmp_path, "    options:\n      tags: [report]\n")
    assert "<svg" in result.html
    assert "<h1>Heading</h1>" not in result.html


def test_a_cell_past_the_end_warns_and_the_rest_still_shows(tmp_path):
    result = render(tmp_path, "    options:\n      cells: '1,99'\n")
    assert "no cell 99 in a 4-cell notebook" in str(result.diagnostics)
    assert "<h1>Heading</h1>" in result.html


def test_an_unparseable_cell_selection_is_an_error(tmp_path):
    result = render(tmp_path, "    options:\n      cells: one to three\n")
    assert result.errors
    assert "is not a cell or cell range" in result.errors[0].message


def test_a_notebook_that_is_not_json_is_reported(tmp_path):
    (tmp_path / "nb.ipynb").write_text("not json", encoding="utf-8")
    (tmp_path / "artifact.yaml").write_text(
        "name: x\nsections:\n  - {type: jupyter, path: nb.ipynb}\n",
        encoding="utf-8",
    )
    result = render_folder(tmp_path)
    assert "not valid notebook JSON" in result.html
    assert result.errors


def test_an_unrun_notebook_says_so_rather_than_rendering_nothing(tmp_path):
    """Empty output is the symptom of a notebook saved before running."""
    result = render(
        tmp_path,
        notebook={
            "nbformat": 4,
            "cells": [{"cell_type": "code", "source": ["x = 1"], "outputs": []}],
        },
    )
    assert "nothing to show" in str(result.diagnostics)
    assert "include_source" in str(result.diagnostics), "and how to fix it"


def test_a_png_output_is_embedded_from_the_notebook_itself(tmp_path):
    """No second file and no file-serving route: images live in the JSON."""
    result = render(
        tmp_path,
        notebook={
            "nbformat": 4,
            "cells": [
                {
                    "cell_type": "code",
                    "source": [],
                    "outputs": [
                        {
                            "output_type": "display_data",
                            "data": {"image/png": "aGVsbG8=\n"},
                        }
                    ],
                }
            ],
        },
    )
    assert 'src="data:image/png;base64,aGVsbG8="' in result.html
