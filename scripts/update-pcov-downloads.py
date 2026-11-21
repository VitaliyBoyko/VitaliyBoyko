#!/usr/bin/env python3
"""Build a Shields.io badge using combined Packagist lifetime installs for PCOV."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

PACKAGES = ("vitaliyboyko/pcov", "magelens/pcov")
OUTPUT = Path(__file__).resolve().parents[1] / "profile/pcov-downloads.json"


def lifetime_downloads(package: str) -> int:
    url = f"https://packagist.org/packages/{quote(package, safe='/')}.json"
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "VitaliyBoyko-profile-badges/1.0"},
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
            details = result["package"]
            if details.get("name", "").lower() != package:
                raise ValueError(f"Unexpected Packagist package for {package}")
            count = details["downloads"]["total"]
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"Invalid Packagist download total for {package}: {count!r}")
            return count
        except (HTTPError, URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Unable to fetch Packagist downloads for {package}")


def main() -> None:
    counts = {package: lifetime_downloads(package) for package in PACKAGES}
    total = sum(counts.values())
    badge = {
        "schemaVersion": 1,
        "label": "PCOV engine downloads",
        "message": f"{total:,}",
        "color": "6366f1",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(badge, indent=2) + "\n"
    if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
        OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Packagist lifetime downloads: {counts}; combined: {total}")


if __name__ == "__main__":
    main()
