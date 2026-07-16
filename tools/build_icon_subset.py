"""Rebuild the bundled Tabler icon subset shipped in the desktop GUI.

Source: @tabler/icons-webfont 3.44.0 (SIL OFL 1.1), via jsDelivr:
  https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.44.0/dist/fonts/tabler-icons.ttf
  https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.44.0/dist/tabler-icons.min.css

The GUI paints only a handful of glyphs (see ``icon()`` in
``scheduleiq/gui/widgets.py``), so the app bundles a subset a few KB in size
instead of the full ~2.8 MB webfont.  The subset keeps each glyph at its
original private-use codepoint and preserves the ``tabler-icons`` family name,
so ``QFont("tabler-icons")`` resolves the same way before and after a rebuild.

To add an icon: add a ``semantic-key -> Tabler-icon-name`` entry to ``ICONS``
below and re-run this script, then paste the printed ``_ICON_CODES`` map into
``scheduleiq/gui/widgets.py``.

Inputs are read from a source directory (``--src DIR`` holding
``tabler-icons.ttf`` and ``tabler-icons.min.css``); if absent, the script
fetches the pinned release into a local cache dir.  Requires fontTools
(``pip install fonttools``).

Usage:
    python tools/build_icon_subset.py [--src DIR]
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

TABLER_VERSION = "3.44.0"
_BASE = f"https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@{TABLER_VERSION}/dist"
TTF_URL = f"{_BASE}/fonts/tabler-icons.ttf"
CSS_URL = f"{_BASE}/tabler-icons.min.css"

# Semantic key used in the app  ->  Tabler icon name (the ``ti-<name>`` class).
# Keys are what ``_ICON_CODES`` exposes to ``icon(name=...)``.
ICONS = {
    "files": "files",
    "report": "gauge",
    "checks": "checklist",
    "trends": "trending-up",
    "paths": "route",
    "forensics": "microscope",
    "settings": "settings",
    "sun": "sun",
    "moon": "moon",
    "plus": "plus",
}

_REPO = Path(__file__).resolve().parent.parent
OUT = _REPO / "src" / "scheduleiq" / "gui" / "assets" / "fonts" / "tabler-icons-subset.ttf"


def _fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "build_icon_subset"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())


def _resolve_inputs(src: Path | None) -> tuple[Path, Path]:
    """Return (ttf_path, css_path), fetching the pinned release if needed."""
    if src is not None:
        ttf = next((p for p in (src / "tabler-icons.ttf",
                                src / "tabler-icons-full.ttf") if p.exists()), None)
        css = next((p for p in (src / "tabler-icons.min.css",
                                src / "tabler-icons.css") if p.exists()), None)
        if ttf and css:
            return ttf, css
        sys.exit(f"--src {src} must contain tabler-icons.ttf and tabler-icons.min.css")
    cache = Path(__file__).resolve().parent / ".icon-cache"
    ttf, css = cache / "tabler-icons.ttf", cache / "tabler-icons.min.css"
    for path, url in ((ttf, TTF_URL), (css, CSS_URL)):
        if not path.exists():
            print(f"fetching {url}")
            try:
                _fetch(url, path)
            except Exception as exc:  # pragma: no cover - network path
                sys.exit(f"could not fetch {url}: {exc}\n"
                         f"Download it manually and pass --src DIR.")
    return ttf, css


def _codepoints(css_text: str) -> dict[str, int]:
    pairs = re.findall(r'ti-([a-z0-9-]+):before\{content:"\\([0-9a-fA-F]+)"\}', css_text)
    return {name: int(cp, 16) for name, cp in pairs}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=None,
                        help="directory holding tabler-icons.ttf + .min.css")
    args = parser.parse_args()

    ttf_path, css_path = _resolve_inputs(args.src)
    name_to_cp = _codepoints(css_path.read_text(encoding="utf-8"))

    key_to_cp: dict[str, int] = {}
    for key, ti_name in ICONS.items():
        cp = name_to_cp.get(ti_name)
        if cp is None:
            sys.exit(f"Tabler {TABLER_VERSION} has no icon named {ti_name!r} "
                     f"(for key {key!r})")
        key_to_cp[key] = cp

    from fontTools import subset
    options = subset.Options()
    options.name_IDs = ["*"]          # keep the 'tabler-icons' family name
    options.notdef_outline = True
    options.recalc_bounds = True
    font = subset.load_font(str(ttf_path), options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=sorted(key_to_cp.values()))
    subsetter.subset(font)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(OUT), options)

    size = OUT.stat().st_size
    print(f"wrote {OUT.relative_to(_REPO)} ({size:,} bytes, "
          f"{len(key_to_cp)} glyphs, Tabler {TABLER_VERSION})")
    print("\nPaste into scheduleiq/gui/widgets.py:\n")
    items = ", ".join(f'"{k}": 0x{cp:04X}' for k, cp in key_to_cp.items())
    print(f"_ICON_CODES = {{\n    {items},\n}}")


if __name__ == "__main__":
    main()
