"""
Payer card ("Дані платника") from cabinet.tax.gov.ua.

GET /ws/api/payer_card returns a list of groups:
  {"idGroup": 1, "title": "...", "type": 1, "headers": {key: label}, "values": {key: value}}
  {"idGroup": 5, "title": "...", "type": 2, "headers": {key: label}, "listValues": [{key: value}, ...]}
Type 1 is a label/value card, type 2 is a table. Group and field names come from the
server, so profile fields are matched by keywords in the labels.
"""

import datetime
import re

from .requisites import REGIONS

PRIMARY_MARKS = {"так", "1", "true", "+", "x", "х", "основний", "основна", "так (основний)"}


def normalize(raw):
    """Keep only well-formed groups, in the shape the template renders."""
    groups = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("headers"), dict):
            continue
        headers = [(str(key), _text(label)) for key, label in item["headers"].items()]
        group = {"id": item.get("idGroup"), "title": _text(item.get("title")), "headers": headers}
        if item.get("type") == 2:
            rows = item.get("listValues") or []
            group["kind"] = "table"
            group["rows"] = [
                [_text(row.get(key)) for key, _ in headers] for row in rows if isinstance(row, dict)
            ]
        else:
            values = item.get("values") or {}
            group["kind"] = "pairs"
            group["pairs"] = [(label, _text(values.get(key))) for key, label in headers]
        groups.append(group)
    return groups


def extract_profile(groups):
    """Map payer card groups to User fields. Only fields that were found are returned."""
    pairs = [
        (_norm(group["title"]), _norm(label), value)
        for group in groups
        for label, value in group.get("pairs", [])
        if value
    ]
    found = {}

    for _, label, value in pairs:
        if "full_name" not in found and _is_full_name(label):
            found["full_name"] = value
        elif "tax_number" not in found and _is_tax_number(label, value):
            found["tax_number"] = re.sub(r"\D", "", value)
        elif "birth_date" not in found and "дата народження" in label:
            found["birth_date"] = _parse_date(value)
        elif "registration_address" not in found and _is_address(label):
            found["registration_address"] = value
        elif "fop_registered_on" not in found and _is_registration_date(label):
            found["fop_registered_on"] = _parse_date(value)
        elif "taken_on_record" not in found and "дата взяття на облік платника податків" in label:
            found["taken_on_record"] = _parse_date(value)
        elif "phone" not in found and label.startswith("телефон"):
            found["phone"] = re.split(r"[,;]", value)[0].strip()
        elif "primary_kved" not in found and "основн" in label and ("квед" in label or "вид" in label):
            found["primary_kved"] = value
        elif _is_tax_office(label):
            if "код" in label:
                found.setdefault("tax_office_code", re.sub(r"\D", "", value) or value)
            else:
                code, name = _split_office(value)
                found.setdefault("tax_office_name", name)
                if code:
                    found.setdefault("tax_office_code", code)

    if "primary_kved" not in found:
        found["primary_kved"] = _primary_kved_from_tables(groups)
    # The cabinet writes KVED codes as "_62.01".
    found["primary_kved"] = re.sub(r"(^|\s)_+(?=\d)", r"\1", found["primary_kved"])

    # The payer card has no state registration date for an entrepreneur; the tax
    # office takes a new ФОП on record right after registration, so that date stands in.
    taken_on_record = found.pop("taken_on_record", None)
    if not found.get("fop_registered_on") and taken_on_record:
        found["fop_registered_on"] = taken_on_record

    profile = {}
    full_name = found.pop("full_name", "")
    if full_name:
        parts = [_capitalize(part) for part in full_name.split()]
        if len(parts) >= 2:
            profile["last_name"], profile["first_name"] = parts[0], parts[1]
            profile["middle_name"] = " ".join(parts[2:])
    for field, value in found.items():
        if value:
            profile[field] = value

    region = _region(profile.get("tax_office_name", "")) or _region(profile.get("registration_address", ""))
    if region:
        profile["tax_region"] = region
    return profile


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _norm(text):
    return re.sub(r"\s+", " ", text.lower().replace("’", "'").replace("ʼ", "'")).strip()


def _is_full_name(label):
    return label in {"піб", "п.і.б."} or ("прізвище" in label and "ім'я" in label) or (
        label.startswith("найменування") and "платник" in label
    )


def _is_tax_number(label, value):
    keyword = any(word in label for word in ("податковий номер", "рнокпп", "дрфо", "реєстраційний номер облікової"))
    return keyword and re.fullmatch(r"\d{10}", re.sub(r"\D", "", value)) is not None


def _is_address(label):
    if "електрон" in label:
        return False
    return "місцезнаходження" in label or "податкова адреса" in label or label.startswith("адреса")


def _is_registration_date(label):
    if "дата" not in label or "реєстрац" not in label:
        return False
    excluded = ("припин", "скасув", "знятт", "пдв", "єдиного податку", "єдиного внеску", "рро", "народження")
    return not any(word in label for word in excluded)


def _is_tax_office(label):
    if "реєстр" in label:
        return False
    return (
        "контролюючий орган" in label
        or "контролюючого органу" in label
        or "дпі" in label
        or "орган дпс" in label
        or "податкова інспекція" in label
    )


def _split_office(value):
    match = re.match(r"^\s*(\d{2,6})\s*[-–—:]?\s*(.+)$", value)
    if match:
        return match.group(1), match.group(2).strip()
    match = re.match(r"^(.+?)\s*\((\d{2,6})\)\s*$", value)
    if match:
        return match.group(2), match.group(1).strip()
    return "", value


def _primary_kved_from_tables(groups):
    for group in groups:
        if "rows" not in group:
            continue
        labels = [_norm(label) for _, label in group["headers"]]
        if not any("квед" in label or ("вид" in label and "діяльн" in label) for label in labels + [_norm(group["title"])]):
            continue
        code_col = next((i for i, l in enumerate(labels) if "код" in l or "квед" in l), None)
        name_col = next((i for i, l in enumerate(labels) if "назва" in l or "найменування" in l), None)
        primary_col = next((i for i, l in enumerate(labels) if "основн" in l), None)
        for row in group["rows"]:
            if primary_col is None or _norm(row[primary_col]) not in PRIMARY_MARKS:
                continue
            parts = [row[col] for col in (code_col, name_col) if col is not None and row[col]]
            if parts:
                return " ".join(dict.fromkeys(parts))
    return ""


def _parse_date(value):
    text = value.strip()
    for pattern, fmt in ((r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y"), (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d")):
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.datetime.strptime(match.group(0), fmt).date()
            except ValueError:
                return None
    return None


def _capitalize(word):
    if not word.isupper():
        return word
    return "-".join(part[:1] + part[1:].lower() for part in word.split("-"))


def _region(text):
    """Region code from "ГУ ДПС у Львівській області" or an address like "Львівська обл., м. Львів"."""
    text = _norm(text)
    for code, name in REGIONS.items():
        if code == "kyiv":
            continue
        adjective = name.split()[0].lower()
        if f"{adjective[:-1]}ій області" in text or f"{adjective} обл" in text:
            return code
    if "києві" in text or "м. київ" in text:
        return "kyiv"
    return ""
