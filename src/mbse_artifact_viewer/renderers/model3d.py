"""The ``3dmodel`` section type: a glTF model in a Three.js viewer.

**glTF only** - ``.glb`` (single file, everything inside) or ``.gltf``
(JSON plus its sibling ``.bin`` and textures). No STEP, no IGES, no
conversion. That is a deliberate scope decision, not a gap: this is a
reference view, so a reviewer can see *which* part is being talked about.
The details live in the drawings, schematics and PDFs alongside it, and
CAD inspection happens in CAD. Converting STEP server-side would put a
few hundred megabytes of OpenCascade into every deployment to render a
picture that an export step produces for free.

So the engineer exports glTF from their CAD, the same way they already
export a PDF drawing. Two things to get right on the way out: glTF's
convention is metres where CAD is usually millimetres, and glTF is Y-up
where CAD is usually Z-up. The ``up`` option covers the second case when
fixing the export isn't practical.

Like ``pdf``, this needs the consumer to offer a file-serving route: the
model is fetched by the browser, not inlined.
"""

from __future__ import annotations

import html
import os

from ..errors import SectionError
from ..registry import RenderContext, renderer
from ..sources import url_for

#: Pinned, and overridable for a network that can't reach a CDN: point
#: MAV_THREE_BASE at a vendored copy of the same layout (``build/`` and
#: ``examples/jsm/`` beneath it) and nothing else changes.
THREE_VERSION = "0.169.0"
THREE_BASE = os.environ.get(
    "MAV_THREE_BASE",
    f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}",
)

EXTENSIONS = (".glb", ".gltf")
DEFAULT_HEIGHT = 480

_IMPORT_MAP = """<script type="importmap">
{{"imports": {{
  "three": "{base}/build/three.module.js",
  "three/addons/": "{base}/examples/jsm/"
}}}}
</script>"""

_VIEWER = """<script type="module">
import * as THREE from "three";
import {{ GLTFLoader }} from "three/addons/loaders/GLTFLoader.js";
import {{ OrbitControls }} from "three/addons/controls/OrbitControls.js";
import {{ RoomEnvironment }} from "three/addons/environments/RoomEnvironment.js";

const mount = document.getElementById("{id}");
const fail = (message) => {{
  mount.innerHTML = '<p class="mav-problem-detail"></p>';
  mount.firstChild.textContent = message;
}};

try {{
  const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(mount.clientWidth, mount.clientHeight);
  mount.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  // An environment map, not just lights: an unlit metallic PBR material
  // renders as a black blob, which is a poor look for a bracket.
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2));
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(1, 2, 1.5);
  scene.add(key);

  const camera = new THREE.PerspectiveCamera(
    45, mount.clientWidth / mount.clientHeight, 0.01, 1000
  );
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  new GLTFLoader().load("{url}", (gltf) => {{
    const model = gltf.scene;
    {up}
    scene.add(model);

    // Frame whatever turned up: a model may be millimetres or metres,
    // centred on the origin or a long way off it.
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3()).length() || 1;
    const centre = box.getCenter(new THREE.Vector3());
    const direction = new THREE.Vector3({camera}).normalize();

    camera.near = size / 100;
    camera.far = size * 100;
    camera.position.copy(centre).addScaledVector(direction, size);
    camera.updateProjectionMatrix();
    controls.target.copy(centre);
    controls.update();
  }}, undefined, (err) => fail("This model could not be loaded: " + err));

  new ResizeObserver(() => {{
    if (!mount.clientWidth) return;
    camera.aspect = mount.clientWidth / mount.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(mount.clientWidth, mount.clientHeight);
  }}).observe(mount);

  renderer.setAnimationLoop(() => {{
    controls.update();
    renderer.render(scene, camera);
  }});
}} catch (err) {{
  fail("This browser could not start a 3D viewer: " + err);
}}
</script>"""


@renderer("3dmodel", options={"camera", "up", "height"})
def render(ctx: RenderContext) -> str:
    path = ctx.require_path()
    resolved = ctx.resolve(path)

    suffix = "." + resolved.rpartition(".")[2].lower()
    if suffix not in EXTENSIONS:
        raise SectionError(
            f"{path!r} is not glTF - this renderer shows "
            f"{' or '.join(EXTENSIONS)} only, so export glTF from your CAD "
            "(a STEP file has to be tessellated before a browser can draw it)"
        )
    if not ctx.source.exists(resolved):
        raise FileNotFoundError(path)

    url = url_for(ctx.source, resolved)
    if url is None:
        raise SectionError(
            "this consumer has no file-serving route, so a 3D model cannot "
            "be displayed - it needs a FileSource with url_for()"
        )

    ctx.require_head("three", _IMPORT_MAP.format(base=THREE_BASE))

    mount = f"mav-3d-{abs(hash((ctx.folder, ctx.section.index))):x}"
    return (
        f'<div class="mav-3d" id="{mount}" '
        f'style="height:{_height(ctx)}px"></div>\n'
        + _VIEWER.format(
            id=mount,
            url=html.escape(url, quote=True),
            up=_up(ctx),
            camera=_camera(ctx),
        )
        + f'\n<p class="mav-caption">Drag to orbit, scroll to zoom · '
        f'<a href="{html.escape(url)}" download>'
        f'{html.escape(path.rpartition("/")[2])}</a></p>'
    )


def _up(ctx: RenderContext) -> str:
    """Rotate a Z-up export into glTF's Y-up world."""
    up = str(ctx.option("up", "y")).lower()
    if up == "y":
        return ""
    if up == "z":
        return "model.rotation.x = -Math.PI / 2;"
    ctx.warn(f"option up={up!r} is not 'y' or 'z'; leaving the model as-is")
    return ""


def _camera(ctx: RenderContext) -> str:
    """The direction to view from - distance is fitted to the model.

    A direction rather than a position, because a position would have to
    be re-guessed for every model: the same ``[1, 1, 1]`` frames a 4 mm
    connector and a 3 m panel.
    """
    value = ctx.option("camera", [1, 1, 1])
    try:
        x, y, z = (float(part) for part in value)
    except (TypeError, ValueError):
        ctx.warn(
            f"option camera={value!r} is not three numbers; using the default"
        )
        x, y, z = 1.0, 1.0, 1.0
    if x == y == z == 0:
        ctx.warn("option camera is all zeroes, which is no direction at all")
        x, y, z = 1.0, 1.0, 1.0
    return f"{x}, {y}, {z}"


def _height(ctx: RenderContext) -> int:
    height = ctx.option("height", DEFAULT_HEIGHT)
    try:
        value = int(height)
    except (TypeError, ValueError):
        ctx.warn(f"option height={height!r} is not a number; using default")
        return DEFAULT_HEIGHT
    if not 100 <= value <= 4000:
        ctx.warn(f"option height={value} is out of range; using default")
        return DEFAULT_HEIGHT
    return value
