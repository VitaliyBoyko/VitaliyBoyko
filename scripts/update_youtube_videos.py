#!/usr/bin/env python3

from __future__ import annotations

import html
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


README_PATH = os.environ.get("README_PATH", "README.md")
START_MARKER = "<!-- youtube-videos:start -->"
END_MARKER = "<!-- youtube-videos:end -->"
MAX_VIDEOS = int(os.environ.get("YOUTUBE_MAX_VIDEOS", "10"))
VIDEOS_PER_ROW = 3

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def build_feed_url() -> str:
    explicit = os.environ.get("YOUTUBE_FEED_URL")
    if explicit:
        return explicit

    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    if channel_id:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    playlist_id = os.environ.get("YOUTUBE_PLAYLIST_ID")
    if playlist_id:
        return f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"

    handle = os.environ.get("YOUTUBE_HANDLE")
    if handle:
        channel_id = resolve_channel_id_from_handle(handle)
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    raise SystemExit(
        "Missing YouTube feed configuration. Set one of "
        "YOUTUBE_FEED_URL, YOUTUBE_CHANNEL_ID, YOUTUBE_PLAYLIST_ID, or YOUTUBE_HANDLE."
    )


def fetch_feed(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "github-actions-youtube-readme-updater/1.0",
            "Accept": "application/atom+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def resolve_channel_id_from_handle(handle: str) -> str:
    normalized = handle.removeprefix("@")
    url = f"https://www.youtube.com/@{normalized}"
    page = fetch_feed(url)
    match = re.search(r'"channelId":"([^"]+)"', page)
    if not match:
        raise SystemExit(f"Could not resolve YouTube channel ID from handle @{normalized}.")
    return match.group(1)


def extract_video_id(entry: ET.Element) -> str | None:
    video_id = entry.findtext("yt:videoId", namespaces=ATOM_NS)
    if video_id:
        return video_id.strip()

    link = entry.find("atom:link[@rel='alternate']", ATOM_NS)
    if link is None:
        return None

    href = link.attrib.get("href", "")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return query.get("v", [None])[0]


def build_video_block(feed_xml: str) -> str:
    root = ET.fromstring(feed_xml)
    videos: list[tuple[str, str]] = []

    for entry in root.findall("atom:entry", ATOM_NS)[:MAX_VIDEOS]:
        title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
        video_id = extract_video_id(entry)
        if not title or not video_id:
            continue

        videos.append((html.escape(title, quote=True), video_id))

    if not videos:
        raise SystemExit("No videos found in the configured YouTube feed.")

    return f"{START_MARKER}\n" + render_video_grid(videos) + f"\n{END_MARKER}"


def render_video_grid(videos: list[tuple[str, str]]) -> str:
    lines = ["<table>"]

    for index in range(0, len(videos), VIDEOS_PER_ROW):
        lines.append("  <tr>")
        for title, video_id in videos[index : index + VIDEOS_PER_ROW]:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            lines.extend(
                [
                    '    <td width="33%" valign="top">',
                    f'      <a href="{video_url}">',
                    f'        <img src="{thumbnail_url}" alt="{title}" width="100%">',
                    "      </a><br>",
                    f'      <strong><a href="{video_url}">{title}</a></strong>',
                    "    </td>",
                ]
            )
        lines.append("  </tr>")

    lines.append("</table>")
    return "\n".join(lines)


def update_readme(readme_path: str, replacement_block: str) -> bool:
    with open(readme_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)
    if not pattern.search(content):
        raise SystemExit(f"Could not find markers {START_MARKER} and {END_MARKER} in {readme_path}.")

    updated = pattern.sub(replacement_block, content, count=1)
    if updated == content:
        return False

    with open(readme_path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    return True


def main() -> int:
    feed_url = build_feed_url()
    feed_xml = fetch_feed(feed_url)
    replacement_block = build_video_block(feed_xml)
    changed = update_readme(README_PATH, replacement_block)
    print("README updated." if changed else "README already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
