#!/usr/bin/env python3
"""Generate a Shields.io badge from lifetime npm downloads for MageLens."""

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

PACKAGES = (
    "@magelens/magento-template-coverage",
)
OUTPUT = Path(__file__).resolve().parents[1] / "profile/template-coverage-downloads.json"
EARLIEST_NPM_DATE = date(2015, 1, 10)


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "VitaliyBoyko-profile-badge/1.0", "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Unable to fetch npm statistics")


def lifetime_downloads(package: str, last_complete_day: date) -> int:
    encoded = quote(package, safe="@")
    metadata = fetch_json(f"https://registry.npmjs.org/{encoded}")
    start = max(date.fromisoformat(metadata["time"]["created"][:10]), EARLIEST_NPM_DATE)
    total = 0

    # npm's downloads API accepts no more than 18 months in one request.
    # Use smaller, non-overlapping periods to preserve the package's whole history.
    while start <= last_complete_day:
        end = min(start + timedelta(days=364), last_complete_day)
        period = f"{start.isoformat()}:{end.isoformat()}"
        result = fetch_json(f"https://api.npmjs.org/downloads/point/{period}/{encoded}")
        count = result.get("downloads")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"Invalid npm download count for {package} in {period}: {count!r}")
        total += count
        start = end + timedelta(days=1)
    return total


def main() -> None:
    # npm processes downloads after the end of the UTC day; allow for reporting lag.
    last_complete_day = datetime.now(timezone.utc).date() - timedelta(days=2)
    counts = {package: lifetime_downloads(package, last_complete_day) for package in PACKAGES}
    total = sum(counts.values())
    badge = {
        "schemaVersion": 1,
        "label": "Template coverage downloads",
        "message": f"{total:,}",
        "color": "6366f1",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(badge, indent=2) + "\n"
    if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
        OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"npm downloads through {last_complete_day}: {counts}; total: {total}")


if __name__ == "__main__":
    main()
