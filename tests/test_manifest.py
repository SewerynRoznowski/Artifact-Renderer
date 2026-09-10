from __future__ import annotations

import pytest

from mbse_artifact_viewer import load_manifest
from mbse_artifact_viewer.errors import ArtifactError
from mbse_artifact_viewer.sources import LocalFileSource


def write(tmp_path, text):
    (tmp_path / "artifact.yaml").write_text(text, encoding="utf-8")
    return LocalFileSource(tmp_path)


def test_parses_ordered_typed_sections(tmp_path):
    source = write(
        tmp_path,
        """
        name: Harness-001
        description: A harness.
        doc: overview.md
        sections:
          - type: wireviz
            path: harness.yaml
            description: As built.
          - type: markdown
            path: notes.md
            options: {depth: 2}
        """,
    )
    manifest, diagnostics = load_manifest(source, "")

    assert diagnostics == []
    assert manifest.name == "Harness-001"
    assert manifest.doc == "overview.md"
    assert [s.type for s in manifest.sections] == ["wireviz", "markdown"]
    assert [s.index for s in manifest.sections] == [0, 1]
    assert manifest.sections[0].description == "As built."
    assert manifest.sections[1].options == {"depth": 2}


def test_a_type_may_repeat_and_order_is_kept(tmp_path):
    source = write(
        tmp_path,
        """
        name: Bracket
        sections:
          - {type: pdf, path: a.pdf}
          - {type: 3dmodel, path: b.glb}
          - {type: pdf, path: c.pdf}
        """,
    )
    manifest, _ = load_manifest(source, "")
    assert [s.path for s in manifest.sections] == ["a.pdf", "b.glb", "c.pdf"]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("", "empty"),
        ("- a\n- b\n", "must be a mapping"),
        ("name: x\n", "no 'sections:'"),
        ("name: x\nsections: 3\n", "must be a list"),
        ("name: x\nsections: [\n", "not valid YAML"),
    ],
)
def test_unrenderable_manifests_are_fatal_for_the_folder(
    tmp_path, text, match
):
    source = write(tmp_path, text)
    with pytest.raises(ArtifactError, match=match):
        load_manifest(source, "")


def test_a_missing_manifest_is_fatal_for_the_folder(tmp_path):
    with pytest.raises(ArtifactError, match="no artifact.yaml"):
        load_manifest(LocalFileSource(tmp_path), "")


def test_unknown_keys_warn_but_do_not_stop_anything(tmp_path):
    source = write(
        tmp_path,
        """
        name: x
        colour: blue
        sections:
          - {type: markdown, path: a.md, flavour: vanilla}
        """,
    )
    manifest, diagnostics = load_manifest(source, "")
    messages = [d.message for d in diagnostics]

    assert len(manifest.sections) == 1
    assert any("'colour'" in m for m in messages)
    assert any("'flavour'" in m for m in messages)


def test_a_malformed_section_becomes_a_placeholder_not_a_failure(tmp_path):
    source = write(
        tmp_path,
        """
        name: x
        sections:
          - "just a string"
          - {path: no-type.md}
          - {type: markdown, path: fine.md}
        """,
    )
    manifest, _ = load_manifest(source, "")

    assert manifest.sections[0].error is not None
    assert "must be a mapping" in manifest.sections[0].error
    assert manifest.sections[1].error == "section has no 'type'"
    assert manifest.sections[2].error is None


def test_name_falls_back_to_the_folder(tmp_path):
    (tmp_path / "Harness-009").mkdir()
    (tmp_path / "Harness-009" / "artifact.yaml").write_text(
        "sections: []\n", encoding="utf-8"
    )
    manifest, _ = load_manifest(LocalFileSource(tmp_path), "Harness-009")
    assert manifest.name == "Harness-009"
