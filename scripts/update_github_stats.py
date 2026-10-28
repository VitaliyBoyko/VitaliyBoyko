#!/usr/bin/env python3
"""Publish a generated stats card only when it contains actual statistics."""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def install_card(candidate: Path, destination: Path) -> None:
    root = ET.fromstring(candidate.read_bytes())
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("Generated card is not an SVG")

    elements = {node.get("data-testid"): node for node in root.iter()}
    if "message" in elements or "Something went wrong" in "".join(root.itertext()):
        raise ValueError("Stats provider returned an error: " + " ".join(root.itertext()).strip())
    for stat in ("stars", "commits", "prs", "issues", "contribs"):
        node = elements.get(stat)
        if node is None or not re.search(r"\d", "".join(node.itertext())):
            raise ValueError(f"Generated card is missing a numeric {stat} statistic")

    readme = Path("README.md")
    updated, count = re.subn(
        r"!\[GitHub Stats\]\(\./profile/stats(?:-[0-9]+)?\.svg\)",
        f"![GitHub Stats](./{destination.as_posix()})",
        readme.read_text(),
    )
    if count != 1:
        raise ValueError("Expected exactly one GitHub Stats image in README.md")

    # Do not modify the published card or README until all validation passes.
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate.replace(destination)
    readme.write_text(updated)
    for old_card in destination.parent.glob("stats*.svg"):
        if old_card != destination and re.fullmatch(r"stats(?:-[0-9]+)?\.svg", old_card.name):
            old_card.unlink()


if __name__ == "__main__":
    try:
        install_card(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"Stats update rejected; keeping the previous card. {error}", file=sys.stderr)
        sys.exit(1)
