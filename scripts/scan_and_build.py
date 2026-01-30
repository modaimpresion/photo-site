#!/usr/bin/env python3
"""Scan inbox images, extract model string, generate a simple static site, and prep for GitHub Pages.

MVP:
- Reads images from ./inbox
- Extracts a "model" key from filename heuristics (will be upgraded to vision/OCR)
- Generates ./site/index.html and per-model pages
- Copies images into ./site/assets/<model>/

Future:
- Use EXIF (Make/Model/LensModel)
- Use OCR/vision to detect model in image content
"""

import os
import re
import shutil
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "inbox"
# GitHub Pages can publish from /docs on the default branch.
SITE = ROOT / "docs"
ASSETS = SITE / "assets"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

MODEL_RE = re.compile(r"(?i)(?:model|型号|type)[\s_\-:]*([A-Za-z0-9][A-Za-z0-9\-_.]{1,32})")


def guess_model_from_filename(name: str) -> str:
    m = MODEL_RE.search(name)
    if m:
        return m.group(1)
    # common pattern: MODEL_xxx.jpg => take prefix before first '_' or '-'
    base = Path(name).stem
    for sep in ("_", "-", " "):
        if sep in base:
            candidate = base.split(sep)[0]
            if 2 <= len(candidate) <= 40:
                return candidate
    return "unknown"


def html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    items = []
    for p in sorted(INBOX.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            model = guess_model_from_filename(p.name)
            items.append((model, p))

    by_model = defaultdict(list)
    for model, p in items:
        by_model[model].append(p)

    # copy + downscale assets for web (keep originals only in inbox)
    # - large: max 1600px
    # - thumb: max 420px
    for model, files in by_model.items():
        dest_dir = ASSETS / model
        thumb_dir = ASSETS / model / "thumb"
        dest_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        for src in files:
            # Always publish JPEGs to keep Pages simple.
            base = Path(src.name).stem
            large_dst = dest_dir / f"{base}.jpg"
            thumb_dst = thumb_dir / f"{base}.jpg"

            def needs_update(dst: Path) -> bool:
                return (not dst.exists()) or (src.stat().st_mtime > dst.stat().st_mtime)

            if needs_update(large_dst):
                tmp = dest_dir / f"{base}.__tmp__.jpg"
                if tmp.exists():
                    tmp.unlink()
                shutil.copy2(src, tmp)
                # sips edits in place
                os.system(f"/usr/bin/sips -s format jpeg --resampleWidth 1600 '{tmp}' >/dev/null")
                tmp.replace(large_dst)

            if needs_update(thumb_dst):
                tmp = thumb_dir / f"{base}.__tmp__.jpg"
                if tmp.exists():
                    tmp.unlink()
                shutil.copy2(src, tmp)
                os.system(f"/usr/bin/sips -s format jpeg --resampleWidth 420 '{tmp}' >/dev/null")
                tmp.replace(thumb_dst)

    # generate pages
    models = sorted(by_model.keys())

    index_parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Photo Library</title>",
        "<style>body{font-family:system-ui, -apple-system, Segoe UI, Roboto, sans-serif;max-width:1100px;margin:24px auto;padding:0 16px} .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px} img{width:100%;height:160px;object-fit:cover;border-radius:10px} a{color:inherit} .card{border:1px solid #eee;border-radius:12px;padding:12px}</style>",
        "</head><body>",
        "<h1>Photo Library</h1>",
        "<p>Auto-grouped by detected model (MVP: filename heuristic). Drop images into <code>photo-site/inbox</code> and rebuild.</p>",
        "<h2>Models</h2>",
        "<div class='grid'>",
    ]

    for model in models:
        count = len(by_model[model])
        href = f"models/{html_escape(model)}.html"
        index_parts.append(f"<div class='card'><a href='{href}'><strong>{html_escape(model)}</strong></a><div>{count} images</div></div>")

    index_parts += ["</div>", "</body></html>"]
    write_file(SITE / "index.html", "\n".join(index_parts))

    for model in models:
        files = by_model[model]
        page = [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
            f"<title>{html_escape(model)} - Photo Library</title>",
            "<style>body{font-family:system-ui, -apple-system, Segoe UI, Roboto, sans-serif;max-width:1100px;margin:24px auto;padding:0 16px} .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px} img{width:100%;height:200px;object-fit:cover;border-radius:10px}</style>",
            "</head><body>",
            "<p><a href='../index.html'>← Back</a></p>",
            f"<h1>Model: {html_escape(model)}</h1>",
            "<div class='grid'>",
        ]
        for src in files:
            base = Path(src.name).stem
            rel_large = f"../assets/{html_escape(model)}/{html_escape(base)}.jpg"
            rel_thumb = f"../assets/{html_escape(model)}/thumb/{html_escape(base)}.jpg"
            page.append(f"<a href='{rel_large}' target='_blank' rel='noopener'><img src='{rel_thumb}' loading='lazy' /></a>")
        page += ["</div>", "</body></html>"]
        write_file(SITE / "models" / f"{model}.html", "\n".join(page))

    print(f"Scanned {len(items)} images across {len(models)} models.")


if __name__ == "__main__":
    main()
