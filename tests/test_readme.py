import pathlib
import re

ROOT = pathlib.Path(__file__).parents[1]


def test_the_readme_install_repeats_docker_compose_yml() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"\n   ```yaml\n(.*?)\n   ```\n", readme, re.DOTALL)
    assert block is not None

    shown = "\n".join(line.removeprefix("   ") for line in block.group(1).splitlines())
    assert shown + "\n" == (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
