# Aadhaar Demo Generator

Generates Aadhaar-style images, scanned PDFs, selectable-text digital PDFs, and matching ground-truth JSON.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
uv --cache-dir .uv-cache pip install --python .venv/bin/python -r requirements.txt
```

## Generate

Generate images plus scanned and digital PDFs:

```bash
uv --cache-dir .uv-cache run python aadhar_demo_generator.py --latest --side both --pdf-type both
```

PDF modes:

```bash
uv --cache-dir .uv-cache run python aadhar_demo_generator.py --latest --side both --pdf-type scanned
uv --cache-dir .uv-cache run python aadhar_demo_generator.py --latest --side both --pdf-type digital
uv --cache-dir .uv-cache run python aadhar_demo_generator.py --latest --side both --pdf-type both
```

`--pdf-type` defaults to `both`. With `--side both`, page 1 is the front and page 2 is the back.

## Outputs

```text
outputs/
├── aadhar/
│   ├── image/
│   └── pdf/
│       ├── scanned/
│       └── digital/
└── ground_truth/
    ├── image/
    └── pdf/
        ├── scanned/
        └── digital/
```

Scanned PDFs contain the 12 image-quality variants. Digital PDFs contain six selectable-text variants:

```text
clean_digital
rotated_page
skewed_text
cropped_page
partial_content
low_contrast_text
```

Every PDF has matching JSON with the same stem and a `pdf_type` value of `scanned` or `digital`. Cropped and partial-content JSON identifies fields intentionally unavailable for accuracy evaluation.

Quality variants: `clean`, `rotated`, `blurred`, `cropped`, `skewed`, `mobile_photo`, `low_light`, `overexposed`, `shadow`, `partial_crop`, `low_resolution`, and `jpeg_heavy_compression`.

## Clear Outputs

```bash
uv --cache-dir .uv-cache run python aadhar_demo_generator.py --clear-output
```

Clear and regenerate:

```bash
uv --cache-dir .uv-cache run python aadhar_demo_generator.py --clear-output --latest --side both --pdf-type both
```
