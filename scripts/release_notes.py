"""Extract the current package version's changelog entry for GitHub Releases."""

import argparse
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def release_notes(project: Path, changelog: Path) -> tuple[str, str]:
    version = tomllib.loads(project.read_text())["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Releases require a stable X.Y.Z version in pyproject.toml")
    entries = re.split(r"(?m)^## ", changelog.read_text())
    matches = []
    for entry in entries[1:]:
        heading, _, body = entry.partition("\n")
        if re.fullmatch(rf"\[{re.escape(version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?", heading.strip()):
            matches.append(body.strip())
    if len(matches) != 1 or not matches[0]:
        raise ValueError(f"Expected one nonempty changelog entry headed '## [{version}]'")
    return version, matches[0] + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    version, notes = release_notes(Path("pyproject.toml"), Path("CHANGELOG.md"))
    args.output.write_text(notes)
    print(version)


if __name__ == "__main__":
    main()
