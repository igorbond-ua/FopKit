"""Payment requisites from the State Tax Service regional pages.

The tax service has no public API for requisites. Each regional subsite publishes
the page "Рахунки для сплати платежів" with two xlsx tables: budget taxes and ЄСВ.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

SINGLE_TAX_CODE = "18050400"
MILITARY_LEVY_CODE = "11011700"
ESV_SELF_EMPLOYED_SYMBOL = "204"

REGIONS = {
    "vin": "Вінницька область",
    "vl": "Волинська область",
    "dp": "Дніпропетровська область",
    "dn": "Донецька область",
    "zt": "Житомирська область",
    "zak": "Закарпатська область",
    "zp": "Запорізька область",
    "if": "Івано-Франківська область",
    "kyivobl": "Київська область",
    "kr": "Кіровоградська область",
    "lg": "Луганська область",
    "lv": "Львівська область",
    "mk": "Миколаївська область",
    "od": "Одеська область",
    "poltava": "Полтавська область",
    "rv": "Рівненська область",
    "sumy": "Сумська область",
    "tr": "Тернопільська область",
    "kh": "Харківська область",
    "kherson": "Херсонська область",
    "km": "Хмельницька область",
    "ck": "Черкаська область",
    "cv": "Чернівецька область",
    "ch": "Чернігівська область",
    "kyiv": "м. Київ",
}

# The tax portal sits behind an Akamai bot filter. It answers 403 "Access Denied" unless the
# request comes over HTTP/2 with the full header set of a desktop browser, Accept-Encoding included.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}
TIMEOUT_SECONDS = 30
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
LINK_RE = re.compile(r'<a\s[^>]*href="(https://[^"]+\.xlsx)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


class RequisitesUnavailable(Exception):
    pass


@dataclass
class Requisite:
    recipient: str
    recipient_code: str
    bank: str
    iban: str
    code: str


def page_url(region):
    return f"https://{region}.tax.gov.ua/rahunki-dlya-splati-platejiv/"


def clean(value):
    return " ".join((value or "").split())


def normalize_place(value):
    # Treasury names mix Latin "i" into Cyrillic words, e.g. "Львiв".
    text = clean(value).lower().replace("i", "і")
    return text.replace("територіальна громада", "тг")


def download(url):
    try:
        with httpx.Client(http2=True, headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                if response.status_code == 403:
                    raise RequisitesUnavailable("Сайт податкової заблокував запит (захист від ботів).")
                if response.status_code != 200:
                    raise RequisitesUnavailable(f"Сайт податкової повернув помилку {response.status_code}.")
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_DOWNLOAD_BYTES:
                        raise RequisitesUnavailable("Файл реквізитів на сайті податкової завеликий.")
    except httpx.HTTPError as exc:
        raise RequisitesUnavailable("Сайт податкової не відповідає.") from exc
    return body


def find_tables(html):
    """Return (taxes_url, esv_url) from a regional requisites page."""
    taxes_url = esv_url = None
    for url, label in LINK_RE.findall(html):
        host = urlsplit(unescape(url)).hostname or ""
        if host != "tax.gov.ua" and not host.endswith(".tax.gov.ua"):
            continue
        text = clean(unescape(TAG_RE.sub(" ", label))).lower()
        if "єдиного внеску" in text and esv_url is None:
            esv_url = unescape(url)
        elif "податків" in text and taxes_url is None:
            taxes_url = unescape(url)
    if not taxes_url or not esv_url:
        raise RequisitesUnavailable("На сторінці податкової не знайдено таблиць реквізитів.")
    return taxes_url, esv_url


def _column_index(ref):
    index = 0
    for char in ref:
        if not char.isalpha():
            break
        index = index * 26 + ord(char.upper()) - ord("A") + 1
    return index - 1


def _text(node):
    return "".join(part.text or "" for part in node.iter(f"{SHEET_NS}t"))


def read_rows(data):
    """Read the first sheet of an xlsx file as lists of cell strings."""
    try:
        book = zipfile.ZipFile(io.BytesIO(data))
        names = book.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
            shared = [_text(item) for item in root.iter(f"{SHEET_NS}si")]
        sheets = sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not sheets:
            raise RequisitesUnavailable("Таблиця реквізитів порожня.")
        root = ElementTree.fromstring(book.read(sheets[0]))
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
        raise RequisitesUnavailable("Не вдалося прочитати таблицю реквізитів.") from exc
    rows = []
    for row in root.iter(f"{SHEET_NS}row"):
        cells = {}
        for position, cell in enumerate(row.findall(f"{SHEET_NS}c")):
            index = _column_index(cell.get("r", "")) if cell.get("r") else position
            value = cell.find(f"{SHEET_NS}v")
            if cell.get("t") == "inlineStr":
                text = _text(cell)
            elif value is None:
                text = ""
            elif cell.get("t") == "s":
                text = shared[int(value.text)]
            else:
                text = value.text or ""
            cells[index] = clean(text)
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def _number(value):
    return value[:-2] if value.endswith(".0") else value


def _columns(rows, matchers):
    """Find the header row and return (row_index, {name: column})."""
    for row_index, row in enumerate(rows):
        headers = [cell.lower() for cell in row]
        found = {}
        for name, match in matchers.items():
            for column, header in enumerate(headers):
                if match(header):
                    found[name] = column
                    break
        if len(found) == len(matchers):
            return row_index, found
    raise RequisitesUnavailable("Формат таблиці реквізитів змінився.")


def _cell(row, column):
    return row[column] if column < len(row) else ""


def _requisite(row, columns, code):
    return Requisite(
        recipient=_cell(row, columns["recipient"]),
        recipient_code=_number(_cell(row, columns["recipient_code"])),
        bank=_cell(row, columns["bank"]),
        iban=_cell(row, columns["iban"]).replace(" ", ""),
        code=code,
    )


def parse_taxes(rows, community):
    """Return {"single_tax": ..., "military_levy": ...} for the community."""
    start, columns = _columns(rows, {
        "place": lambda h: "населений пункт" in h,
        "recipient": lambda h: h == "отримувач",
        "recipient_code": lambda h: "єдрпоу" in h,
        "bank": lambda h: h.startswith("банк отримувача"),
        "iban": lambda h: "iban" in h,
        "code": lambda h: h.startswith("код класифікації доходів"),
    })
    wanted = normalize_place(community)
    targets = {wanted, f"{wanted} тг"}
    single_tax = None
    levy_rows = []
    for row in rows[start + 1:]:
        code = _number(_cell(row, columns["code"]))
        local = normalize_place(_cell(row, columns["place"])) in targets
        if code == SINGLE_TAX_CODE and local and single_tax is None:
            single_tax = _requisite(row, columns, code)
        elif code == MILITARY_LEVY_CODE:
            levy_rows.append((local, row))
    if single_tax is None:
        raise RequisitesUnavailable(f"У таблиці податкової немає рахунку єдиного податку для громади «{community}».")
    if not levy_rows:
        raise RequisitesUnavailable("У таблиці податкової немає рахунку військового збору.")
    levy_rows.sort(key=lambda item: not item[0])
    return {
        "single_tax": single_tax,
        "military_levy": _requisite(levy_rows[0][1], columns, MILITARY_LEVY_CODE),
    }


def parse_esv(rows):
    start, columns = _columns(rows, {
        "recipient": lambda h: "(отримувач)" in h,
        "recipient_code": lambda h: "єдрпоу" in h,
        "bank": lambda h: h.startswith("банк отримувача"),
        "iban": lambda h: "iban" in h,
        "code": lambda h: h.startswith("символ звітності"),
    })
    for row in rows[start + 1:]:
        if _number(_cell(row, columns["code"])) == ESV_SELF_EMPLOYED_SYMBOL:
            return _requisite(row, columns, ESV_SELF_EMPLOYED_SYMBOL)
    raise RequisitesUnavailable("У таблиці податкової немає рахунку ЄСВ для ФОП.")


def fetch(region, community):
    """Download and parse requisites for the region subsite and territorial community."""
    if region not in REGIONS:
        raise RequisitesUnavailable("Невідома область.")
    html = download(page_url(region)).decode("utf-8", errors="replace")
    taxes_url, esv_url = find_tables(html)
    result = parse_taxes(read_rows(download(taxes_url)), community)
    result["esv"] = parse_esv(read_rows(download(esv_url)))
    return result
