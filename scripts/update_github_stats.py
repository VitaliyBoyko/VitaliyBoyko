#!/usr/bin/env python3
"""Publish a generated stats card only when it contains actual statistics."""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


PROJECT_REPOSITORIES = (
    "MageLens/MageLens",
    "magento/magento2-phpstorm-plugin",
)
STAR_LABEL = "Stars across my projects"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NAMESPACE)


def additional_project_stars(owner: str) -> int:
    """Count explicitly selected projects outside the profile owner's namespace."""
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", owner):
        raise ValueError("A valid profile owner is required")

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    total = 0
    seen = set()
    for repository in PROJECT_REPOSITORIES:
        request = Request(f"https://api.github.com/repos/{repository}", headers=headers)
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid repository response for {repository}")
        repository_id = data.get("id")
        stars = data.get("stargazers_count")
        repository_owner = data.get("owner")
        login = repository_owner.get("login") if isinstance(repository_owner, dict) else None
        if (
            type(repository_id) is not int or repository_id <= 0
            or type(stars) is not int or stars < 0
            or not isinstance(login, str) or not login
        ):
            raise ValueError(f"Missing or invalid star metadata for {repository}")
        if repository_id not in seen and login.casefold() != owner.casefold():
            total += stars
        seen.add(repository_id)
    return total


def install_card(candidate: Path, destination: Path, owner: str) -> None:
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

    stars = elements["stars"]
    base_stars = "".join(stars.itertext()).strip()
    if not re.fullmatch(r"[0-9]+", base_stars):
        raise ValueError("The stars statistic must be an exact integer; use number_format=long")
    labels = [node for node in root.iter() if node.text == "Total Stars Earned:"]
    description = root.find(f"{{{SVG_NAMESPACE}}}desc")
    if len(labels) != 1 or description is None:
        raise ValueError("Expected an unmodified stats card with a star label and description")

    total_stars = int(base_stars) + additional_project_stars(owner)
    description.text, count = re.subn(
        r"Total Stars Earned: [0-9]+(?=,|$)",
        f"{STAR_LABEL}: {total_stars}",
        description.text or "",
    )
    if count != 1:
        raise ValueError("Expected exactly one stars statistic in the card description")
    labels[0].text = f"{STAR_LABEL}:"
    stars.text = str(total_stars)

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
    candidate.write_bytes(ET.tostring(root, encoding="utf-8"))
    candidate.replace(destination)
    readme.write_text(updated)
    for old_card in destination.parent.glob("stats*.svg"):
        if old_card != destination and re.fullmatch(r"stats(?:-[0-9]+)?\.svg", old_card.name):
            old_card.unlink()


if __name__ == "__main__":
    try:
        install_card(Path(sys.argv[1]), Path(sys.argv[2]), os.environ.get("PROFILE_OWNER", ""))
    except (OSError, ValueError, ET.ParseError, URLError) as error:
        print(f"Stats update rejected; keeping the previous card. {error}", file=sys.stderr)
        sys.exit(1)

