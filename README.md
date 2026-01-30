# photo-site

Drop images into `photo-site/inbox/`.

Run:

```bash
./scripts/scan_and_build.py
```

It generates a static site in `photo-site/docs/` (GitHub Pages-friendly).

MVP model detection: filename heuristic.
Planned upgrades:
- EXIF Make/Model/LensModel
- OCR/vision-based model detection from the image content
- Image resizing to fit GitHub Pages limits
