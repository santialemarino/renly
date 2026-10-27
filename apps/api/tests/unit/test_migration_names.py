import ast
import re
from pathlib import Path

# Every Alembic migration is `migrations/versions/NNNN_<slug>.py`, its `revision` is the file's stem and
# its `down_revision` the previous file's, so filename order IS the order Alembic applies them — which
# `test_notification_event_surface.py` relies on, and which CI's baseline stamp (`0001_baseline`) names.
# `migrate:make` writes a random hex id and a hex-prefixed file, so a migration committed without the
# rename would break the chain silently until a deploy tried to upgrade. Read statically: no Alembic import.

_VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
_NAME = re.compile(r"^(\d{4})_[a-z0-9]+(?:_[a-z0-9]+)*$")


# Each migration file, in filename order, as (stem, revision, down_revision).
def _migrations() -> list[tuple[str, object, object]]:
    found = []
    for path in sorted(_VERSIONS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        ids = {}
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in ("revision", "down_revision"):
                    ids[node.targets[0].id] = ast.literal_eval(node.value)
        found.append((path.stem, ids.get("revision", "<missing>"), ids.get("down_revision", "<missing>")))
    return found


class TestMigrationChain:
    def test_the_population_is_real(self):
        migrations = _migrations()
        assert len(migrations) >= 32
        assert migrations[0][0] == "0001_baseline"

    def test_every_file_is_named_nnnn_slug(self):
        assert [stem for stem, _, _ in _migrations() if not _NAME.match(stem)] == []

    def test_numbers_are_consecutive_from_one(self):
        numbers = [int(stem[:4]) for stem, _, _ in _migrations()]
        assert numbers == list(range(1, len(numbers) + 1))

    def test_revision_is_the_file_stem(self):
        assert [(stem, revision) for stem, revision, _ in _migrations() if revision != stem] == []

    def test_down_revision_is_the_previous_file(self):
        migrations = _migrations()
        expected = [None] + [stem for stem, _, _ in migrations[:-1]]
        assert [(stem, down) for (stem, _, down), want in zip(migrations, expected, strict=True) if down != want] == []

    def test_the_chain_is_linear_with_one_head(self):
        migrations = _migrations()
        revisions = {revision for _, revision, _ in migrations}
        parents = [down for _, _, down in migrations if down is not None]
        # Nothing branches (no revision is revised twice) and exactly one revision is revised by nothing.
        assert len(parents) == len(set(parents))
        assert len(revisions - set(parents)) == 1
