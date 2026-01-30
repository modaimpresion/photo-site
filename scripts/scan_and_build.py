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

# Extract model codes like D5301-1 / ABC123 etc.
MODEL_RE = re.compile(r"(?i)(?:model|型号|type)[\s_\-:：]*([A-Za-z0-9][A-Za-z0-9\-_.]{1,32})")

# Also accept bare model codes at start of filename like: D5301-1.HEIC
BARE_MODEL_PREFIX_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9\-_.]{1,32})$")

# Cache OCR results to avoid rescanning the same files every build.
OCR_CACHE_PATH = ROOT / "output" / "ocr-cache.json"


def sanitize_model_code(model: str) -> str:
    m = (model or "").strip().upper()
    m = re.sub(r"[^A-Z0-9._-]+", "-", m)
    m = re.sub(r"-+", "-", m)
    m = m.strip("-._")
    return m or "UNKNOWN"


def guess_model_from_filename(name: str) -> str:
    m = MODEL_RE.search(name)
    if m:
        return m.group(1)

    base = Path(name).stem

    # If filename is exactly a model code, accept it.
    if BARE_MODEL_PREFIX_RE.match(base):
        # But ignore camera roll defaults.
        if re.match(r"(?i)^img_\d+$", base):
            return "unknown"
        return base

    # Ignore generic camera roll names.
    if re.match(r"(?i)^img_\d+$", base):
        return "unknown"

    # common pattern: MODEL_xxx.jpg => take prefix before first '_' or '-'
    for sep in ("_", "-", " "):
        if sep in base:
            candidate = base.split(sep)[0]
            if 2 <= len(candidate) <= 40 and not re.match(r"(?i)^img$", candidate):
                return candidate

    return "unknown"


def html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def load_ocr_cache() -> dict:
    try:
        if OCR_CACHE_PATH.exists():
            import json
            return json.loads(OCR_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_ocr_cache(cache: dict) -> None:
    OCR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    import json
    OCR_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def ocr_text_for_image(path: Path, cache: dict) -> str:
    """Run macOS Vision OCR (swift script) on the given image.

    We OCR the *published large jpeg* whenever possible for consistency.
    Cache key: absolute path + mtime.
    """
    key = str(path.resolve())
    mtime = int(path.stat().st_mtime)
    entry = cache.get(key)
    if isinstance(entry, dict) and entry.get("mtime") == mtime and isinstance(entry.get("text"), str):
        return entry["text"]

    swift = ROOT / "scripts" / "ocr_text.swift"
    cmd = ["/usr/bin/env", "swift", str(swift), str(path)]
    try:
        import subprocess
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=45)
        text = out.decode("utf-8", errors="ignore")
    except Exception:
        text = ""

    cache[key] = {"mtime": mtime, "text": text}
    return text


def extract_model_from_text(text: str) -> str:
    """Try to extract model from OCR text."""
    if not text:
        return "unknown"

    # Normalize a bit
    t = text.replace("\u3000", " ")

    m = MODEL_RE.search(t)
    if m:
        return m.group(1)

    # Prefer leading model-like token at the start of the text, e.g. "D5301-1 ..."
    lead = re.match(r"\s*([A-Z0-9][A-Z0-9\-_.]{2,32})\b", t.upper())
    if lead:
        cand = lead.group(1)
        if not re.match(r"^IMG_\d+$", cand):
            return cand

    # Extra heuristics: pick short tokens that look like model codes.
    candidates = re.findall(r"\b[A-Z0-9][A-Z0-9\-_.]{2,32}\b", t.upper())
    blacklist = {"WWW", "HTTP", "HTTPS", "MADE", "CHINA", "APPLE", "IPHONE", "IOS", "PCS", "S", "M", "L", "XL", "XXL"}
    candidates = [c for c in candidates if c not in blacklist and not re.match(r"^IMG_\d+$", c)]
    if candidates:
        return candidates[0]

    return "unknown"


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    ocr_cache = load_ocr_cache()

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
    # NOTE: We also OCR the large JPEG (Vision) to re-classify "unknown" models.

    # First pass: create assets in a temporary "unknown" bucket for anything we can't name yet.
    tmp_by_model = defaultdict(list)
    for model, files in by_model.items():
        tmp_by_model[model].extend(files)

    for model, files in tmp_by_model.items():
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
                os.system(f"/usr/bin/sips -s format jpeg --resampleWidth 1600 '{tmp}' >/dev/null")
                tmp.replace(large_dst)

            if needs_update(thumb_dst):
                tmp = thumb_dir / f"{base}.__tmp__.jpg"
                if tmp.exists():
                    tmp.unlink()
                shutil.copy2(src, tmp)
                os.system(f"/usr/bin/sips -s format jpeg --resampleWidth 420 '{tmp}' >/dev/null")
                tmp.replace(thumb_dst)

    # Second pass: OCR images that landed in "unknown" and re-bucket.
    if "unknown" in tmp_by_model:
        reclassified = defaultdict(list)
        unknown_files = tmp_by_model["unknown"]
        # Safety: OCR can be slow; cap per run.
        OCR_CAP = int(os.environ.get("OCR_CAP", "4"))
        for i, src in enumerate(unknown_files[:OCR_CAP], start=1):
            base = Path(src.name).stem
            large_jpg = ASSETS / "unknown" / f"{base}.jpg"
            print(f"OCR {i}/{min(len(unknown_files), OCR_CAP)}: {src.name}", flush=True)
            text = ocr_text_for_image(large_jpg, ocr_cache)
            new_model = sanitize_model_code(extract_model_from_text(text))
            reclassified[new_model].append(src)

        # Anything beyond OCR_CAP remains unknown for now.
        for src in unknown_files[OCR_CAP:]:
            reclassified["UNKNOWN"].append(src)

        # Move assets from unknown -> model buckets when we found something.
        for new_model, files in reclassified.items():
            if new_model in ("UNKNOWN", "unknown"):
                continue
            (ASSETS / new_model / "thumb").mkdir(parents=True, exist_ok=True)
            (ASSETS / new_model).mkdir(parents=True, exist_ok=True)

            for src in files:
                base = Path(src.name).stem
                src_large = ASSETS / "unknown" / f"{base}.jpg"
                src_thumb = ASSETS / "unknown" / "thumb" / f"{base}.jpg"
                dst_large = ASSETS / new_model / f"{base}.jpg"
                dst_thumb = ASSETS / new_model / "thumb" / f"{base}.jpg"
                if src_large.exists():
                    shutil.move(str(src_large), str(dst_large))
                if src_thumb.exists():
                    shutil.move(str(src_thumb), str(dst_thumb))

        # Rename source files in inbox to <MODEL>.HEIC whenever possible.
        # This makes future runs deterministic without OCR.
        for new_model, files in reclassified.items():
            if new_model in ("UNKNOWN", "unknown"):
                continue
            for src in files:
                if src.suffix.lower() != ".heic":
                    continue
                # If already clean name, skip.
                if src.stem.upper() == new_model:
                    continue
                target = INBOX / f"{new_model}.HEIC"
                if target.exists():
                    # Avoid collisions.
                    target = INBOX / f"{new_model}_{src.name}"
                try:
                    src.rename(target)
                except Exception:
                    pass

        # Rebuild by_model mapping based on reclassified results
        by_model = defaultdict(list)
        for model, files in tmp_by_model.items():
            if model != "unknown":
                for f in files:
                    by_model[sanitize_model_code(model)].append(f)
        for model, files in reclassified.items():
            for f in files:
                by_model[sanitize_model_code(model)].append(f)

    save_ocr_cache(ocr_cache)

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
            # Directly show the large image inline (no extra click needed).
            # Keep a link to the file for saving/opening in a new tab.
            page.append(
                f"<figure style='margin:0'>"
                f"<a href='{rel_large}' target='_blank' rel='noopener'>"
                f"<img src='{rel_large}' loading='lazy' />"
                f"</a>"
                f"</figure>"
            )
        page += ["</div>", "</body></html>"]
        write_file(SITE / "models" / f"{model}.html", "\n".join(page))

    print(f"Scanned {len(items)} images across {len(models)} models.", flush=True)


if __name__ == "__main__":
    main()
