# Every place that installs uv installs the SAME version: the API image (`docker/api.Dockerfile`) and
# each CI workflow. uv is what reads uv.lock, and a CI job on another uv than the image can resolve
# or refuse the lock differently from the build it is meant to vouch for.
#
# The population is DERIVED: every uv install in the Dockerfiles and the workflow files — a
# `pip install uv…` or a `ghcr.io/astral-sh/uv:<tag>` image — so a new workflow that installs uv is
# held to the pin without being listed here, and one that installs it unpinned fails rather than going
# unseen. The `astral-sh/setup-uv` action is refused outright: its version lives in a `with:` block
# this does not parse, so a workflow installs uv the way the others do.

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_DOCKERFILES = sorted((_REPO / "docker").glob("*Dockerfile*"))
_WORKFLOWS = sorted((_REPO / ".github" / "workflows").glob("*.y*ml"))

# An install, and the version it names (None when it names none).
_PIP_INSTALL = re.compile(r"pip3? install\b[^\n]*?\buv\b(?:==([\w.]+))?")
_IMAGE = re.compile(r"ghcr\.io/astral-sh/uv(?::([\w.]+))?")
_SETUP_ACTION = re.compile(r"astral-sh/setup-uv@")


# Every uv install in the repo's build files, as (file:line, version or None).
def _installs() -> list[tuple[str, str | None]]:
    found = []
    for path in [*_DOCKERFILES, *_WORKFLOWS]:
        text = path.read_text()
        name = path.relative_to(_REPO)
        for pattern in (_PIP_INSTALL, _IMAGE):
            for match in pattern.finditer(text):
                found.append((f"{name}:{text.count(chr(10), 0, match.start()) + 1}", match.group(1)))
        for match in _SETUP_ACTION.finditer(text):
            found.append((f"{name}:{text.count(chr(10), 0, match.start()) + 1}", None))
    return found


# The population: the image and both workflows that install uv today.
def test_derives_the_uv_installs():
    installs = _installs()
    print(f"uv installs: {installs}")
    files = {site.split(":")[0] for site, _ in installs}
    assert "docker/api.Dockerfile" in files
    assert len(files) >= 3, files


# Every install names a version, and it is the image's.
def test_every_uv_install_matches_the_image():
    installs = _installs()
    unpinned = [site for site, version in installs if version is None]
    assert unpinned == [], f"pin uv to the version docker/api.Dockerfile copies in: {unpinned}"
    image = [version for site, version in installs if site.startswith("docker/api.Dockerfile:")]
    assert len(image) == 1, image
    drifted = [f"{site} installs uv {version}" for site, version in installs if version != image[0]]
    assert drifted == [], f"docker/api.Dockerfile installs uv {image[0]}: {drifted}"
