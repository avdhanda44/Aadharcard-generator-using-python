# Aadharcard-generator-using-python
This is a Python project that collects form details and generates a demo Aadhaar-style preview.

The original project runs from `Aadhar generator.ipynb` in Jupyter Notebook.

This repo now also includes a Python 3 GUI script that saves the front demo output as PNG and PDF:

```bash
source .venv/bin/activate
python aadhar_demo_generator.py
```

After clicking **Save Front PNG + PDF**, files are saved in:

```text
outputs/aadhar/
```

An empty folder is also kept for future labels/metadata:

```text
outputs/ground_truth/
```

You can also export the latest saved database record without opening the GUI:

```bash
python aadhar_demo_generator.py --latest
```

The command exports the front by default. You can choose the side:

```bash
python aadhar_demo_generator.py --latest --side front
python aadhar_demo_generator.py --latest --side back
python aadhar_demo_generator.py --latest --side both
```

Saved data remains in:

```text
AadharForm.db
```

Generated outputs are clearly marked `DEMO / NOT VALID ID` in the header/footer so OCR fields remain readable.

The form also has an optional `Photo Path` field. If you provide a local image path, the front side uses that image; otherwise it creates a neutral sample photo placeholder.

The front side uses an Aadhaar-inspired layout for OCR testing: emblem, brush header, large photo, details, QR code, number, and slogan band.

Front output uses:

```text
lastname_firstname_yyyymmdd_id_front.png
lastname_firstname_yyyymmdd_id_front.pdf
```

Back output uses:

```text
lastname_firstname_yyyymmdd_id_back.png
lastname_firstname_yyyymmdd_id_back.pdf
```
