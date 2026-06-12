import argparse
import io
import json
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from tkinter import Button, Entry, IntVar, Label, OptionMenu, StringVar, Tk, messagebox

import pyqrcode
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageTk


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "AadharForm.db"
OUTPUT_DIR = BASE_DIR / "outputs"
AADHAR_OUTPUT_DIR = OUTPUT_DIR / "aadhar"
GROUND_TRUTH_DIR = OUTPUT_DIR / "ground_truth"
QR_PATH = AADHAR_OUTPUT_DIR / "latest_qr.png"

IMAGE_VARIANTS = {
    "clean": "png",
    "rotated": "png",
    "blurred": "png",
    "cropped": "png",
    "skewed": "png",
    "mobile_photo": "jpg",
    "low_light": "png",
    "overexposed": "png",
    "shadow": "png",
    "partial_crop": "png",
    "low_resolution": "png",
    "jpeg_heavy_compression": "jpg",
}


FIELDS = [
    ("Full Name", "fullname"),
    ("Hindi Name", "hindi_name"),
    ("Father Name", "fathername"),
    ("Email", "email"),
    ("Mobile Number", "mobile"),
    ("Date of Birth", "dob"),
    ("House Number", "house"),
    ("Street Name", "street"),
    ("City", "city"),
    ("State", "state"),
    ("Pincode", "pincode"),
    ("Photo Path (optional)", "photo_path"),
]


def font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/NotoSansOriya.ttc",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def devanagari_font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
        "/System/Library/Fonts/Supplemental/ITFDevanagari.ttc",
        "/System/Library/Fonts/Supplemental/DevanagariMT.ttc",
        "/System/Library/Fonts/Kohinoor.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return font(size, bold=bold)


def ensure_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS Iden1 (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Fullname TEXT,
                Fathername TEXT,
                Email TEXT,
                Gender TEXT,
                Bloodgroup TEXT,
                MobileNumber INTEGER,
                DateofBirth TEXT,
                HouseNumber TEXT,
                StreetName TEXT,
                City TEXT,
                State TEXT,
                Pincode INTEGER
            )
            """
        )


def save_record(data):
    ensure_database()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Iden1 (
                FullName, FatherName, Email, Gender, Bloodgroup, MobileNumber,
                DateofBirth, HouseNumber, StreetName, City, State, Pincode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["fullname"],
                data["fathername"],
                data["email"],
                data["gender"],
                data["bloodgroup"],
                data["mobile"],
                data["dob"],
                data["house"],
                data["street"],
                data["city"],
                data["state"],
                data["pincode"],
            ),
        )
        conn.commit()
        return cursor.lastrowid


def latest_record():
    ensure_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM Iden1 ORDER BY Id DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def record_to_data(record):
    gender_map = {"1": "MALE", "2": "FEMALE", 1: "MALE", 2: "FEMALE"}
    return {
        "id": record["Id"],
        "fullname": record["Fullname"],
        "hindi_name": hindi_name_for(record["Fullname"]),
        "fathername": record["Fathername"],
        "relationship_type": "father",
        "relationship_label": "Father",
        "relationship_name": record["Fathername"],
        "relationship_hindi_name": hindi_name_for(record["Fathername"]),
        "email": record["Email"],
        "gender": gender_map.get(record["Gender"], str(record["Gender"])),
        "bloodgroup": record["Bloodgroup"],
        "mobile": record["MobileNumber"],
        "dob": record["DateofBirth"],
        "dob_display": "yob",
        "house": record["HouseNumber"],
        "street": record["StreetName"],
        "city": record["City"],
        "state": record["State"],
        "pincode": record["Pincode"],
        "photo_path": "",
    }


def aadhaar_number(record_id):
    return f"{record_id:04d} {record_id + 3064:04d} {record_id + 5067:04d}"


def transliterate_to_devanagari(text):
    mapping = {
        "aa": "आ", "ai": "ऐ", "au": "औ", "ee": "ई", "oo": "ऊ",
        "kh": "ख", "gh": "घ", "ch": "च", "jh": "झ", "th": "थ", "dh": "ध", "ph": "फ", "bh": "भ", "sh": "श", "ng": "ङ", "ny": "ञ",
        "a": "अ", "b": "ब", "c": "क", "d": "द", "e": "ए", "f": "फ", "g": "ग", "h": "ह", "i": "इ", "j": "ज", "k": "क", "l": "ल", "m": "म", "n": "न", "o": "ओ", "p": "प", "q": "क", "r": "र", "s": "स", "t": "त", "u": "उ", "v": "व", "w": "व", "x": "क्स", "y": "य", "z": "ज",
    }
    text = str(text).strip().lower()
    result = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            result.append(" ")
            i += 1
            continue
        # Try longest matches first
        matched = False
        for length in (3, 2, 1):
            if i + length <= len(text):
                chunk = text[i : i + length]
                if chunk in mapping:
                    result.append(mapping[chunk])
                    i += length
                    matched = True
                    break
        if not matched:
            result.append(text[i])
            i += 1
    return "".join(result)


def hindi_name_for(name):
    known_names = {
        "aarav": "आरव",
        "mehta": "मेहता",
        "anuradha": "अनुराधा",
        "kumari": "कुमारी",
        "rohan": "रोहन",
        "sharma": "शर्मा",
        "verma": "वर्मा",
        "singh": "सिंह",
        "patil": "पाटिल",
        "nair": "नायर",
    }
    words = str(name).strip().split()
    translated = []
    for word in words:
        lower = word.lower()
        if lower in known_names:
            translated.append(known_names[lower])
        else:
            translated.append(transliterate_to_devanagari(lower))
    return " ".join(translated)


def hindi_address_part(value):
    known_parts = {
        "lotus": "लोटस",
        "park": "पार्क",
        "road": "रोड",
        "pune": "पुणे",
        "maharashtra": "महाराष्ट्र",
        "mumbai": "मुंबई",
        "delhi": "दिल्ली",
        "bangalore": "बेंगलुरु",
        "bengaluru": "बेंगलुरु",
        "chennai": "चेन्नई",
        "hyderabad": "हैदराबाद",
        "kolkata": "कोलकाता",
    }
    text = str(value).strip()
    if not text:
        return text

    words = text.split()
    translated_words = []
    for word in words:
        lower = word.lower()
        if lower in known_parts:
            translated_words.append(known_parts[lower])
        else:
            translated_words.append(transliterate_to_devanagari(word))

    return " ".join(translated_words)


def gender_label(value):
    normalized = str(value).strip().lower()
    if normalized in {"1", "male", "पुरुष"}:
        return "पुरुष / Male"
    if normalized in {"2", "female", "महिला"}:
        return "महिला / Female"
    return str(value)


def dob_display_mode(data):
    mode = str(data.get("dob_display") or "yob").strip().lower()
    if mode == "random":
        return random.Random(int(data.get("id") or 0) + 17).choice(["dob", "yob"])
    if mode in {"dob", "date_of_birth"}:
        return "dob"
    return "yob"


def front_birth_label(data):
    if dob_display_mode(data) == "dob":
        return f"जन्म तिथि / DOB : {data['dob']}"
    return f"जन्म वर्ष / Year of Birth : {format_year(data['dob'])}"


def relationship_label_for(data):
    label = str(data.get("relationship_label") or data.get("relationship_type") or "Father").strip()
    normalized = label.lower().replace(".", "").replace(" ", "_")

    if normalized in {"s/o", "so", "son_of"}:
        return "S/O"
    if normalized in {"c/o", "co", "care_of", "care-of"}:
        return "C/O"
    if normalized in {"w/o", "wo", "wife_of"}:
        return "W/O"
    if normalized == "husband":
        return "Husband"
    return "Father"


def relationship_type_for(data):
    label = relationship_label_for(data)
    if label in {"Husband", "W/O"}:
        return "husband"
    if label == "C/O":
        return "care_of"
    return "father"


def relationship_value_for(data):
    return str(data.get("relationship_name") or data.get("fathername") or "").strip()


def relationship_hindi_value_for(data):
    value = str(data.get("relationship_hindi_name") or "").strip()
    if value:
        return value
    relationship_value = relationship_value_for(data)
    return hindi_name_for(relationship_value) if relationship_value else ""


def relationship_hindi_label_for(data):
    label = relationship_label_for(data)
    if label == "S/O":
        return "पुत्र"
    if label == "C/O":
        return "मार्फत"
    if label == "W/O":
        return "पत्नी"
    if label == "Husband":
        return "पति"
    return "पिता"


def hindi_address_for(data):
    lines = ["पता:"]
    relationship_value = relationship_hindi_value_for(data)
    if relationship_value:
        lines.append(f"{relationship_hindi_label_for(data)}: {relationship_value}")

    house = str(data.get('house') or '').strip()
    street = str(data.get('street') or '').strip()
    if house or street:
        joined = ", ".join([part for part in [house, hindi_address_part(street)] if part])
        lines.append(joined)

    city = hindi_address_part(data.get('city') or '')
    state = hindi_address_part(data.get('state') or '')
    if city or state:
        lines.append(", ".join(part for part in [city, state] if part))

    pincode = str(data.get('pincode') or '').strip()
    if pincode:
        lines.append(pincode)
    return lines


def english_address_for(data):
    lines = []
    relationship_value = relationship_value_for(data)
    if relationship_value:
        lines.append(f"{relationship_label_for(data)}: {relationship_value}")

    house = str(data.get('house') or '').strip()
    street = str(data.get('street') or '').strip()
    if house or street:
        lines.append(", ".join(part for part in [house, street] if part))

    city = str(data.get('city') or '').strip()
    state = str(data.get('state') or '').strip()
    if city or state:
        lines.append(", ".join(part for part in [city, state] if part))

    pincode = str(data.get('pincode') or '').strip()
    if pincode:
        lines.append(pincode)
    return lines


def draw_text(draw, xy, text, fill="black", size=18, bold=False):
    draw.text(xy, str(text), fill=fill, font=font(size, bold=bold))


def draw_hindi_text(draw, xy, text, fill="black", size=18, bold=False):
    draw.text(xy, str(text), fill=fill, font=devanagari_font(size, bold=bold))


def paste_asset(canvas, filename, box):
    path = BASE_DIR / filename
    paste_image(canvas, path, box)


def paste_image(canvas, path, box):
    if not path.exists():
        return
    image = Image.open(path).convert("RGBA")
    image.thumbnail((box[2], box[3]))
    canvas.alpha_composite(image, (box[0], box[1]))


def paste_photo(canvas, data, box):
    x, y, width, height = box
    photo_path = data.get("photo_path")
    if photo_path and Path(photo_path).expanduser().exists():
        photo = Image.open(Path(photo_path).expanduser()).convert("RGB")
        photo.thumbnail((width, height))
        background = Image.new("RGB", (width, height), "#f1f1f1")
        offset = ((width - photo.width) // 2, (height - photo.height) // 2)
        background.paste(photo, offset)
    else:
        background = Image.new("RGB", (width, height), "#e7eef5")
        photo_draw = ImageDraw.Draw(background)
        photo_draw.ellipse((width * 0.34, height * 0.15, width * 0.66, height * 0.45), fill="#9aa7b5")
        photo_draw.rounded_rectangle((width * 0.20, height * 0.48, width * 0.80, height * 0.92), radius=18, fill="#9aa7b5")
        photo_draw.text((12, height - 22), "SAMPLE PHOTO", fill="#56616d", font=font(12, bold=True))

    canvas.alpha_composite(background.convert("RGBA"), (x, y))


def brush_stroke(draw, xy, fill):
    x1, y1, x2, y2 = xy
    mid = (y1 + y2) // 2
    points = [
        (x1 + 8, mid - 12),
        (x1 + 30, y1 + 3),
        (x2 - 80, y1 + 8),
        (x2 - 25, mid - 4),
        (x2 - 2, mid + 1),
        (x2 - 42, mid + 11),
        (x1 + 42, y2 - 4),
        (x1, mid + 9),
    ]
    draw.polygon(points, fill=fill)
    for offset in range(0, 16, 4):
        draw.line((x1 + 25 + offset, y1 + offset // 2, x2 - 75, y1 + 5 + offset), fill=fill, width=3)


def draw_phone_icon(draw, x, y):
    draw.arc((x, y, x + 42, y + 30), 180, 360, fill="#222222", width=6)
    draw.rectangle((x + 8, y + 20, x + 34, y + 38), fill="#222222")
    for index in range(3):
        for col in range(3):
            draw.ellipse((x + 13 + col * 7, y + 23 + index * 5, x + 16 + col * 7, y + 26 + index * 5), fill="white")


def draw_mail_icon(draw, x, y):
    draw.rectangle((x, y, x + 58, y + 38), outline="#222222", width=4)
    draw.line((x, y, x + 29, y + 24, x + 58, y), fill="#222222", width=3)
    draw.line((x, y + 38, x + 22, y + 19), fill="#222222", width=2)
    draw.line((x + 58, y + 38, x + 36, y + 19), fill="#222222", width=2)


def draw_www_icon(draw, x, y):
    draw.rounded_rectangle((x, y, x + 70, y + 36), radius=4, fill="#222222")
    draw_text(draw, (x + 9, y + 4), "WWW", fill="white", size=20, bold=True)


def draw_location_icon(draw, x, y):
    draw.line((x, y + 2, x + 40, y + 42), fill="#222222", width=7)
    draw.line((x + 7, y, x + 47, y + 40), fill="#555555", width=3)


def format_year(value):
    match = re.search(r"(19|20)\d{2}", str(value))
    return match.group(0) if match else str(value)


def create_card_image(data):
    AADHAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    record_id = int(data["id"])
    card_number = aadhaar_number(record_id)
    qr = pyqrcode.create(f"DEMO\n{card_number}\n{data['fullname']}\n{data['mobile']}")
    qr.png(str(QR_PATH), scale=4)

    width, height = 900, 600
    canvas = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    draw.rectangle((0, 0, width, height), fill="#fbfbf6")
    draw.rectangle((6, 6, width - 6, height - 6), outline="#111111", width=2)

    brush_stroke(draw, (255, 30, 765, 78), "#f59a22")
    brush_stroke(draw, (260, 80, 777, 125), "#42b84e")

    paste_asset(canvas, "INDIANEMBLEM.png", (102, 26, 78, 78))

    draw_hindi_text(draw, (418, 36), "भारत सरकार", fill="#2b1a10", size=35, bold=True)
    draw_text(draw, (370, 84), "GOVERNMENT OF INDIA", fill="#073d16", size=33, bold=True)
    photo_box = (52, 152, 210, 270)
    draw.rectangle((photo_box[0] - 2, photo_box[1] - 2, photo_box[0] + photo_box[2] + 2, photo_box[1] + photo_box[3] + 2), outline="#e5e5df", width=2)
    paste_photo(canvas, data, photo_box)

    text_x = 285
    hindi_name = data.get("hindi_name") or hindi_name_for(data["fullname"])
    draw_hindi_text(draw, (text_x, 146), hindi_name, size=29, bold=True)
    draw_text(draw, (text_x, 190), data["fullname"], size=29)
    draw_hindi_text(draw, (text_x, 263), front_birth_label(data), size=27)
    draw_hindi_text(draw, (text_x, 318), gender_label(data["gender"]), size=27)

    qr_box = (650, 250, 205, 205)
    draw.rectangle((qr_box[0] - 8, qr_box[1] - 8, qr_box[0] + qr_box[2] + 8, qr_box[1] + qr_box[3] + 8), fill="#fbfbf6")
    paste_image(canvas, QR_PATH, qr_box)

    draw_text(draw, (270, 470), card_number, size=43, bold=True)
    draw.line((0, 525, width, 525), fill="#e1221d", width=4)
    draw_hindi_text(draw, (115, 548), "आधार", fill="#e1221d", size=39, bold=True)
    draw_hindi_text(draw, (250, 548), "- आम आदमी का अधिकार", fill="#222222", size=39, bold=True)
    
    return canvas.convert("RGB")


def create_back_card_image(data):
    AADHAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    record_id = int(data["id"])
    card_number = aadhaar_number(record_id)

    width, height = 900, 600
    canvas = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    draw.rectangle((0, 0, width, height), fill="#fbfbf6")
    draw.rounded_rectangle((8, 8, width - 8, height - 8), radius=16, outline="#111111", width=2)

    paste_asset(canvas, "Aadhaar.png", (78, 35, 110, 82))
    brush_stroke(draw, (250, 34, 750, 72), "#f59a22")
    brush_stroke(draw, (255, 76, 760, 112), "#42b84e")
    draw_hindi_text(draw, (350, 38), "भारतीय विशिष्ट पहचान प्राधिकरण", fill="#9c2b22", size=23, bold=True)
    draw_text(draw, (285, 80), "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", fill="#073d16", size=23, bold=True)

    left_x, right_x = 55, 470
    top_y = 165
    for index, line in enumerate(hindi_address_for(data)):
        draw_hindi_text(draw, (left_x, top_y + index * 37), line, size=24 if index == 0 else 22, bold=index == 0)
    for index, line in enumerate(english_address_for(data)):
        draw_text(draw, (right_x, top_y + index * 37), line, size=24 if index == 0 else 22, bold=index == 0)

    draw_text(draw, (285, 430), card_number, size=39, bold=True)
    draw.line((0, 480, width, 480), fill="#e1221d", width=4)

    draw_phone_icon(draw, 115, 500)
    draw_text(draw, (110, 545), "1947", size=17, bold=True)
    draw_text(draw, (82, 568), "1800 180 1947", size=17, bold=True)

    draw_mail_icon(draw, 330, 501)
    draw_text(draw, (280, 552), "help@uidai.gov.in", size=17, bold=True)

    draw_www_icon(draw, 540, 503)
    draw_text(draw, (500, 552), "www.uidai.gov.in", size=17, bold=True)

    draw_location_icon(draw, 730, 501)
    draw_text(draw, (690, 545), "P.O. Box No. 1947,", size=16, bold=True)
    draw_text(draw, (690, 568), "Bengaluru-560 001", size=16, bold=True)
    
    return canvas.convert("RGB")


def normalized_date(value):
    digits = re.sub(r"\D+", "", str(value))
    if len(digits) == 8:
        if digits[:4].startswith(("19", "20")):
            return digits
        return f"{digits[4:8]}{digits[2:4]}{digits[0:2]}"
    year = format_year(value)
    return f"{year}0000"


def output_stem(data, side):
    parts = re.findall(r"[A-Za-z0-9]+", str(data["fullname"]).lower())
    first_name = parts[0] if parts else "unknown"
    last_name = parts[-1] if len(parts) > 1 else first_name
    dob = normalized_date(data["dob"])
    return f"{last_name}_{first_name}_{side}_{dob}"


def full_address_for_ground_truth(data):
    parts = [
        data.get("house"),
        data.get("street"),
        data.get("city"),
        data.get("state"),
        data.get("pincode"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def full_hindi_address_for_ground_truth(data):
    parts = [
        data.get("house"),
        hindi_address_part(data.get("street") or ""),
        hindi_address_part(data.get("city") or ""),
        hindi_address_part(data.get("state") or ""),
        data.get("pincode"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def address_parts_for_ground_truth(data):
    return {
        "house": str(data.get("house", "")),
        "street": str(data.get("street", "")),
        "city": str(data.get("city", "")),
        "state": str(data.get("state", "")),
        "pincode": str(data.get("pincode", "")),
    }


def ground_truth_payload(data, side, variant, source_file):
    record_id = int(data["id"])

    if side == "front":
        display_mode = dob_display_mode(data)
        return {
            "aadhaar_number": aadhaar_number(record_id),
            "vid": "",
            "name": data["fullname"],
            "hindi_name": data.get("hindi_name") or hindi_name_for(data["fullname"]),
            "date_of_birth": data["dob"] if display_mode == "dob" else "",
            "year_of_birth": format_year(data["dob"]) if display_mode == "yob" else "",
            "gender": data["gender"],
        }

    if side == "back":
        relationship_type = relationship_type_for(data)
        relationship_label = relationship_label_for(data)
        relationship_value = relationship_value_for(data)
        relationship_hindi_label = relationship_hindi_label_for(data)
        relationship_hindi_value = relationship_hindi_value_for(data)
        return {
            "aadhaar_number": aadhaar_number(record_id),
            "vid": "",
            "relationship_label": relationship_label,
            "care_of": relationship_value if relationship_type == "care_of" else "",
            "father_name": relationship_value if relationship_type == "father" else "",
            "husband_name": relationship_value if relationship_type == "husband" else "",
            "hindi_relationship_label": relationship_hindi_label,
            "hindi_care_of": relationship_hindi_value if relationship_type == "care_of" else "",
            "hindi_father_name": relationship_hindi_value if relationship_type == "father" else "",
            "hindi_husband_name": relationship_hindi_value if relationship_type == "husband" else "",
            "address": full_address_for_ground_truth(data),
            "hindi_address": full_hindi_address_for_ground_truth(data),
            "hindi_address_lines": hindi_address_for(data),
            "pincode": str(data.get("pincode", "")),
        }

    raise ValueError("side must be one of: front, back")


def save_ground_truth(data, side, variant, source_file):
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    path = GROUND_TRUTH_DIR / f"{output_stem(data, side)}_{variant}.json"
    payload = ground_truth_payload(data, side, variant, source_file)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")
    return path


def perspective_coeffs(src, dst):
    matrix = []
    values = []
    for (sx, sy), (dx, dy) in zip(src, dst):
        matrix.append([sx, sy, 1, 0, 0, 0, -dx * sx, -dx * sy])
        values.append(dx)
        matrix.append([0, 0, 0, sx, sy, 1, -dy * sx, -dy * sy])
        values.append(dy)

    for col in range(8):
        pivot = max(range(col, 8), key=lambda row: abs(matrix[row][col]))
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        values[col], values[pivot] = values[pivot], values[col]
        divisor = matrix[col][col] or 1
        matrix[col] = [value / divisor for value in matrix[col]]
        values[col] /= divisor
        for row in range(8):
            if row == col:
                continue
            factor = matrix[row][col]
            matrix[row] = [
                current - factor * pivot_value
                for current, pivot_value in zip(matrix[row], matrix[col])
            ]
            values[row] -= factor * values[col]

    return tuple(values)


def apply_skew(image, rng):
    width, height = image.size
    margin = int(min(width, height) * 0.08)
    src = [(0, 0), (width, 0), (width, height), (0, height)]
    dst = [
        (rng.randint(0, margin), rng.randint(0, margin)),
        (width - rng.randint(0, margin), rng.randint(0, margin)),
        (width - rng.randint(0, margin), height - rng.randint(0, margin)),
        (rng.randint(0, margin), height - rng.randint(0, margin)),
    ]
    coeffs = perspective_coeffs(src, dst)
    return image.transform(
        image.size,
        Image.PERSPECTIVE,
        coeffs,
        resample=Image.BICUBIC,
        fillcolor=(245, 245, 240),
    )


def apply_crop(image, rng):
    width, height = image.size
    left = rng.randint(8, 32)
    top = rng.randint(8, 28)
    right = width - rng.randint(8, 32)
    bottom = height - rng.randint(8, 28)
    cropped = image.crop((left, top, right, bottom))
    return cropped.resize((width, height), Image.Resampling.LANCZOS)


def add_mobile_lighting(image, rng):
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.86, 1.14))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.82, 1.20))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    draw.ellipse(
        (-width * 0.15, -height * 0.2, width * 0.65, height * 0.65),
        fill=(255, 255, 255, 28),
    )
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def apply_low_light(image, rng):
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.42, 0.62))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.82, 1.08))
    return image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.7)))


def apply_overexposed(image, rng):
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(1.38, 1.72))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.72, 0.92))
    return image


def apply_shadow(image, rng):
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = base.size
    side = rng.choice(["left", "right", "top"])

    if side == "left":
        points = [(0, 0), (int(width * 0.48), 0), (int(width * 0.24), height), (0, height)]
    elif side == "right":
        points = [(width, 0), (int(width * 0.58), 0), (int(width * 0.78), height), (width, height)]
    else:
        points = [(0, 0), (width, 0), (width, int(height * 0.34)), (0, int(height * 0.52))]

    draw.polygon(points, fill=(0, 0, 0, rng.randint(70, 115)))
    return Image.alpha_composite(base, overlay).convert("RGB")


def apply_partial_crop(image, rng):
    width, height = image.size
    crop_side = rng.choice(["left", "right", "top", "bottom"])
    crop_ratio = rng.uniform(0.08, 0.18)
    left, top, right, bottom = 0, 0, width, height

    if crop_side == "left":
        left = int(width * crop_ratio)
    elif crop_side == "right":
        right = int(width * (1 - crop_ratio))
    elif crop_side == "top":
        top = int(height * crop_ratio)
    else:
        bottom = int(height * (1 - crop_ratio))

    cropped = image.crop((left, top, right, bottom))
    canvas = Image.new("RGB", (width, height), (238, 238, 232))
    canvas.paste(cropped.resize((right - left, bottom - top), Image.Resampling.LANCZOS), (left, top))
    return canvas


def apply_low_resolution(image, rng):
    width, height = image.size
    scale = rng.uniform(0.28, 0.42)
    small = image.resize((int(width * scale), int(height * scale)), Image.Resampling.BILINEAR)
    return small.resize((width, height), Image.Resampling.BILINEAR)


def apply_jpeg_heavy_compression(image, rng):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=rng.randint(12, 24), optimize=True)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def variant_images(image, seed):
    rng = random.Random(seed)
    clean = image.copy()
    rotated = image.rotate(
        rng.uniform(-9, 9),
        expand=True,
        fillcolor=(245, 245, 240),
        resample=Image.BICUBIC,
    )
    blurred = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(1.6, 3.2)))
    cropped = apply_crop(image, rng)
    skewed = apply_skew(image, rng)
    mobile_photo = add_mobile_lighting(apply_skew(image, rng), rng)
    mobile_photo = mobile_photo.rotate(
        rng.uniform(-4, 4),
        expand=False,
        fillcolor=(230, 230, 225),
        resample=Image.BICUBIC,
    ).filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.6, 1.4)))

    return {
        "clean": clean,
        "rotated": rotated,
        "blurred": blurred,
        "cropped": cropped,
        "skewed": skewed,
        "mobile_photo": mobile_photo,
        "low_light": apply_low_light(image, rng),
        "overexposed": apply_overexposed(image, rng),
        "shadow": apply_shadow(image, rng),
        "partial_crop": apply_partial_crop(image, rng),
        "low_resolution": apply_low_resolution(image, rng),
        "jpeg_heavy_compression": apply_jpeg_heavy_compression(image, rng),
    }


def save_variant_image(image, path, ext):
    if ext == "jpg":
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=68, optimize=True)
        path.write_bytes(buffer.getvalue())
        return
    image.save(path)


def export_side(data, side, image, paths):
    stem = output_stem(data, side)
    seed = int(data["id"]) * 1000 + (1 if side == "front" else 2)

    for variant, variant_image in variant_images(image, seed).items():
        ext = IMAGE_VARIANTS[variant]
        image_path = AADHAR_OUTPUT_DIR / f"{stem}_{variant}.{ext}"
        save_variant_image(variant_image, image_path, ext)
        json_path = save_ground_truth(data, side, variant, image_path)
        paths[f"{side}_{variant}_{ext}"] = image_path
        paths[f"{side}_{variant}_json"] = json_path

    pdf_path = AADHAR_OUTPUT_DIR / f"{stem}.pdf"
    image.save(pdf_path, "PDF", resolution=100.0)
    paths[f"{side}_pdf"] = pdf_path


def build_data_from_args(args):
    data = {
        "id": args.record_id or 0,
        "fullname": (args.fullname or "").strip(),
        "hindi_name": (args.hindi_name or "").strip(),
        "fathername": (args.fathername or "").strip(),
        "relationship_type": (args.relationship_type or "father").strip(),
        "relationship_label": (args.relationship_label or args.relationship_type or "Father").strip(),
        "relationship_name": (args.relationship_name or args.fathername or "").strip(),
        "relationship_hindi_name": (args.relationship_hindi_name or "").strip(),
        "email": (args.email or "").strip(),
        "gender": (args.gender or "1").strip(),
        "bloodgroup": (args.bloodgroup or "A+").strip(),
        "mobile": (args.mobile or "").strip(),
        "dob": (args.dob or "").strip(),
        "dob_display": (args.dob_display or "yob").strip(),
        "house": (args.house or "").strip(),
        "street": (args.street or "").strip(),
        "city": (args.city or "").strip(),
        "state": (args.state or "").strip(),
        "pincode": (args.pincode or "").strip(),
        "photo_path": (args.photo_path or "").strip(),
    }

    if not data["hindi_name"]:
        data["hindi_name"] = hindi_name_for(data["fullname"])

    normalized = str(data["gender"]).strip().lower()
    if normalized in {"1", "male", "m", "पुरुष"}:
        data["gender"] = "MALE"
    elif normalized in {"2", "female", "f", "महिला"}:
        data["gender"] = "FEMALE"
    else:
        data["gender"] = data["gender"].upper()

    return data


def prompt_for_inputs():
    def ask(field_name, default="", required=False):
        while True:
            prompt_text = f"{field_name}"
            if default:
                prompt_text += f" [{default}]"
            prompt_text += ": "
            value = input(prompt_text).strip()
            if not value and default:
                value = default
            if required and not value:
                print("This field is required.")
                continue
            return value

    print("Enter Aadhaar record details. Leave optional fields blank.")
    print("Date of birth format: YYYY-MM-DD")
    data = {
        "id": int(ask("Record ID (optional, integer)", "0") or 0),
        "fullname": ask("Full name", required=True),
        "hindi_name": ask("Hindi name (optional)"),
        "relationship_label": ask("Relationship label (Father/S/O/C/O/W/O/Husband)", "Father"),
        "relationship_name": ask("Relationship name", required=True),
        "relationship_hindi_name": ask("Relationship Hindi name (optional)"),
        "email": ask("Email (optional)"),
        "gender": ask("Gender (1=Male, 2=Female)", "1"),
        "bloodgroup": ask("Blood group", "A+"),
        "mobile": ask("Mobile number (digits)", required=True),
        "dob": ask("Date of birth (YYYY-MM-DD)", required=True),
        "dob_display": ask("DOB display on front (yob/dob/random)", "yob"),
        "house": ask("House number (optional)"),
        "street": ask("Street name (optional)"),
        "city": ask("City", required=True),
        "state": ask("State", required=True),
        "pincode": ask("Pincode (6 digits)", required=True),
        "photo_path": ask("Photo path (optional)"),
    }

    if not data["hindi_name"]:
        data["hindi_name"] = hindi_name_for(data["fullname"])

    data["fathername"] = data["relationship_name"]

    normalized = str(data["gender"]).strip().lower()
    if normalized in {"1", "male", "m", "पुरुष"}:
        data["gender"] = "MALE"
    elif normalized in {"2", "female", "f", "महिला"}:
        data["gender"] = "FEMALE"
    else:
        data["gender"] = data["gender"].upper()

    return data


def clear_previous_outputs():
    AADHAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    for path in AADHAR_OUTPUT_DIR.glob("*"):
        if path.is_file():
            if path.name == ".gitkeep":
                continue
            path.unlink()
    if QR_PATH.exists():
        QR_PATH.unlink()


def export_card(data, side="front"):
    if side not in {"front", "back", "both"}:
        raise ValueError("side must be one of: front, back, both")

    AADHAR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}

    if side in {"front", "both"}:
        front_image = create_card_image(data)
        export_side(data, "front", front_image, paths)

    if side in {"back", "both"}:
        back_image = create_back_card_image(data)
        export_side(data, "back", back_image, paths)

    if QR_PATH.exists():
        QR_PATH.unlink()
    return paths


def run_gui():
    root = Tk()
    root.geometry("500x940")
    root.title("Demo Aadhaar Card Generator")
    root.configure(background="lightblue")

    values = {}
    for index, (label, key) in enumerate(FIELDS):
        y = 35 + index * 50
        Label(root, bg="lightblue", text=label, width=20, font=("Arial", 10, "bold")).place(x=45, y=y)
        values[key] = StringVar()
        Entry(root, textvar=values[key], width=28).place(x=230, y=y)

    option_y = 35 + len(FIELDS) * 50

    Label(root, bg="lightblue", text="Gender", width=20, font=("Arial", 10, "bold")).place(x=45, y=option_y)
    gender = IntVar(value=1)
    OptionMenu(root, gender, 1, 2).place(x=230, y=option_y - 5)
    Label(root, bg="lightblue", text="1 = Male, 2 = Female").place(x=285, y=option_y)

    Label(root, bg="lightblue", text="Blood Group", width=20, font=("Arial", 10, "bold")).place(x=45, y=option_y + 50)
    bloodgroup = StringVar(value="A+")
    OptionMenu(root, bloodgroup, "A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-").place(x=230, y=option_y + 45)

    preview_label = Label(root, bg="lightblue")
    preview_label.place(x=145, y=option_y + 140)

    def submit():
        data = {key: value.get().strip() for key, value in values.items()}
        if not data["hindi_name"]:
            data["hindi_name"] = hindi_name_for(data["fullname"])
        data["gender"] = gender.get()
        data["bloodgroup"] = bloodgroup.get()
        required = ["fullname", "fathername", "mobile", "dob", "city", "state", "pincode"]
        missing = [key for key in required if not data[key]]
        if missing:
            messagebox.showerror("Missing details", "Please fill all required fields.")
            return

        record_id = save_record(data)
        data["id"] = record_id
        data["gender"] = "MALE" if data["gender"] == 1 else "FEMALE"
        paths = export_card(data)

        preview = Image.open(paths["front_clean_png"])
        preview.thumbnail((210, 130))
        preview_image = ImageTk.PhotoImage(preview)
        preview_label.configure(image=preview_image)
        preview_label.image = preview_image
        messagebox.showinfo(
            "Saved",
            "Front clean PNG:\n{front_clean_png}\n\nFront PDF:\n{front_pdf}".format(**paths),
        )

    Button(root, text="Save Front PNG + PDF", width=30, bg="brown", fg="white", command=submit).place(x=125, y=option_y + 100)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Generate demo Aadhaar-style PNG and PDF outputs.")
    parser.add_argument("--latest", action="store_true", help="Export the latest saved database record.")
    parser.add_argument(
        "--side",
        choices=("front", "back", "both"),
        default="both",
        help="Which side to export. Default: both.",
    )
    parser.add_argument("--record-id", type=int, default=0, help="Integer ID used to generate a demo Aadhaar number and output filename.")
    parser.add_argument("--fullname", help="Full name for the generated record.")
    parser.add_argument("--hindi-name", dest="hindi_name", help="Hindi name for the generated record.")
    parser.add_argument("--fathername", help="Father's name for the generated record.")
    parser.add_argument(
        "--relationship-type",
        choices=("father", "husband", "care_of", "s/o", "c/o", "w/o"),
        default="father",
        help="Backward-compatible relationship type for the back side.",
    )
    parser.add_argument(
        "--relationship-label",
        choices=("Father", "S/O", "C/O", "W/O", "Husband"),
        default=None,
        help="Exact relationship label printed on the back side.",
    )
    parser.add_argument("--relationship-name", help="Relationship name printed on the back side.")
    parser.add_argument("--relationship-hindi-name", help="Hindi relationship name printed on the back side.")
    parser.add_argument("--email", help="Email address for the generated record.")
    parser.add_argument("--gender", help="Gender value for the generated record (1/2/male/female).")
    parser.add_argument("--bloodgroup", help="Blood group for the generated record.")
    parser.add_argument("--mobile", help="Mobile phone number for the generated record.")
    parser.add_argument("--dob", help="Date of birth for the generated record.")
    parser.add_argument(
        "--dob-display",
        choices=("yob", "dob", "random"),
        default="yob",
        help="Birth field printed on the front side.",
    )
    parser.add_argument("--house", help="House number for the generated record.")
    parser.add_argument("--street", help="Street name for the generated record.")
    parser.add_argument("--city", help="City for the generated record.")
    parser.add_argument("--state", help="State for the generated record.")
    parser.add_argument("--pincode", help="Pincode for the generated record.")
    parser.add_argument("--photo-path", help="Optional photo path for the generated record.")
    parser.add_argument("--prompt", action="store_true", help="Ask for input values interactively in the terminal.")
    args = parser.parse_args()

    if args.latest:
        record = latest_record()
        if not record:
            raise SystemExit("No records found in AadharForm.db yet.")
        data = record_to_data(record)
    elif args.prompt:
        data = prompt_for_inputs()
    elif args.fullname:
        data = build_data_from_args(args)
        required = ["fullname", "mobile", "dob", "city", "state", "pincode"]
        missing = [key for key in required if not data[key]]
        if missing:
            raise SystemExit(f"Missing required fields for generation: {', '.join(missing)}")
    else:
        run_gui()
        return

    paths = export_card(data, side=args.side)
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
