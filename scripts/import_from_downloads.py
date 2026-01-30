#!/usr/bin/env python3
"""Import photos from ~/Downloads/**/照片/** into photo-site.

- Files with recognizable model codes (D5301-xx etc.) should already have been imported.
- This script focuses on the remaining ones: name them by "品名" (product name).

Policy (per Master Wei):
- If we can't detect a model code from filename, still import it.
- Name it by product name (default: filename stem). If collisions, append _2, _3...
- Infer big category from path keywords: 套装/裤子/裙子->连衣裙, else 套装.
- Archive originals under ~/Downloads/_imported_to_photo_site/<timestamp>/...

Safe: copies archived file into inbox; originals are moved into archive.
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime

DOWNLOADS = Path.home() / "Downloads"
ROOT = Path("/Users/wei/.openclaw/workspace/photo-site")
INBOX = ROOT / "inbox"
CATMAP_PATH = ROOT / "output" / "category-map.json"

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

PAT_NUM = re.compile(r"^(?:D)?(\d{4})-(\d{1,2})", re.I)
PAT_DCODE = re.compile(r"^D\d{4}-\d{2}$", re.I)
PAT_D5 = re.compile(r"^D\d{5}$", re.I)


def norm_model_from_stem(stem: str):
    s = stem.upper().strip()
    s = re.sub(r"[^A-Z0-9-]+", "", s)  # drop # and other marks
    if PAT_D5.match(s):
        return s
    m = PAT_NUM.match(s)
    if m:
        prefix = "D" + m.group(1)
        num = m.group(2)
        if len(num) == 1:
            num = "0" + num
        return f"{prefix}-{num}"
    if PAT_DCODE.match(s):
        return s
    return None


def product_name_from_file(p: Path) -> str:
    # Use filename stem as product name; keep digits/alnum.
    name = p.stem.strip()
    # remove trailing markers like '#'
    name = name.replace('#', '').strip()
    # collapse spaces
    name = re.sub(r"\s+", " ", name)
    return name or "UNNAMED"


def safe_code_from_name(name: str) -> str:
    # Keep it URL/file safe but preserve digits.
    s = name.upper().strip()
    # For pure digits, keep digits.
    if re.fullmatch(r"\d{2,10}", s):
        return s
    # Otherwise allow A-Z0-9 and '-' only.
    s = re.sub(r"[^A-Z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "UNKNOWN"


def infer_big_from_path(p: Path) -> str:
    sp = str(p)
    if "套装" in sp:
        return "套装"
    if "裤子" in sp:
        return "裤子"
    if "裙子" in sp:
        return "连衣裙"
    return "套装"


def family_key(code: str) -> str:
    m = re.match(r"^([A-Z]+\d{4})", code)
    return m.group(1) if m else code.split("-")[0].upper()


def main():
    INBOX.mkdir(parents=True, exist_ok=True)

    # Load category map
    if CATMAP_PATH.exists():
        catmap = json.loads(CATMAP_PATH.read_text(encoding="utf-8"))
    else:
        catmap = {"_meta": {"note": ""}, "defaults": {"big": "套装"}, "models": {}}
    catmap.setdefault("models", {})

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = DOWNLOADS / "_imported_to_photo_site" / stamp
    archive.mkdir(parents=True, exist_ok=True)

    candidates = []
    for p in DOWNLOADS.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in EXTS:
            continue
        sp = str(p)
        if "i4ToolsDownloads" in sp:
            continue
        if "/照片/" not in sp and "\\照片\\" not in sp:
            continue
        candidates.append(p)

    moved = 0
    recognized = 0
    named = 0

    for p in sorted(candidates):
        model = norm_model_from_stem(p.stem)
        if model:
            # Already handled by the earlier import typically; skip if already exists in inbox.
            dest = INBOX / (model + p.suffix.upper())
            if dest.exists():
                continue
            code = model
            recognized += 1
        else:
            pname = product_name_from_file(p)
            code = safe_code_from_name(pname)
            named += 1

        big = infer_big_from_path(p)
        sub = family_key(code)
        catmap["models"][code] = {"big": big, "sub": sub}

        # choose destination filename (allow multiple per code)
        dest = INBOX / (code + p.suffix.upper())
        if dest.exists():
            i = 2
            while True:
                dest = INBOX / f"{code}_{i}{p.suffix.upper()}"
                if not dest.exists():
                    break
                i += 1

        # move original into archive, preserve relative path
        rel = p.relative_to(DOWNLOADS)
        arch = archive / rel
        arch.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(arch))

        # copy archived file into inbox
        shutil.copy2(str(arch), str(dest))
        moved += 1

    CATMAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATMAP_PATH.write_text(json.dumps(catmap, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Imported {moved} files from Downloads/**/照片/**")
    print(f" - recognized model codes: {recognized}")
    print(f" - named by 品名 (filename): {named}")
    print(f"Archive: {archive}")


if __name__ == "__main__":
    main()
