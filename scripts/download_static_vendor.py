#!/usr/bin/env python3
"""Download pinned browser vendor assets used by Django static files."""

from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "lab" / "static"

ASSETS = {
    "vendor/css/daisyui.min.css": "https://cdn.jsdelivr.net/npm/daisyui@4.12.10/dist/full.min.css",
    "vendor/css/pedigreejs.v5.0.0.min.css": "https://raw.githubusercontent.com/CCGE-BOADICEA/pedigreejs/master/build/pedigreejs.v5.0.0.min.css",
    "vendor/js/d3.v7.9.0.min.js": "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js",
    "vendor/js/jquery-3.7.1.min.js": "https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js",
    "vendor/js/pedigreejs.v5.0.0.min.js": "https://raw.githubusercontent.com/CCGE-BOADICEA/pedigreejs/master/build/pedigreejs.v5.0.0.min.js",
    "vendor/fontawesome/LICENSE.txt": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/LICENSE.txt",
    "vendor/fontawesome/css/all.min.css": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/css/all.min.css",
    "vendor/fontawesome/webfonts/fa-brands-400.woff2": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-brands-400.woff2",
    "vendor/fontawesome/webfonts/fa-regular-400.woff2": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-regular-400.woff2",
    "vendor/fontawesome/webfonts/fa-solid-900.woff2": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-solid-900.woff2",
    "vendor/fontawesome/webfonts/fa-brands-400.ttf": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-brands-400.ttf",
    "vendor/fontawesome/webfonts/fa-regular-400.ttf": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-regular-400.ttf",
    "vendor/fontawesome/webfonts/fa-solid-900.ttf": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-solid-900.ttf",
    "vendor/fontawesome/webfonts/fa-v4compatibility.woff2": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-v4compatibility.woff2",
    "vendor/fontawesome/webfonts/fa-v4compatibility.ttf": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.1/webfonts/fa-v4compatibility.ttf",
}


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "RareIndex static vendor downloader"})
    with urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())


def main() -> None:
    for relative_path, url in ASSETS.items():
        destination = STATIC / relative_path
        print(f"Downloading {relative_path}")
        download(url, destination)


if __name__ == "__main__":
    main()
