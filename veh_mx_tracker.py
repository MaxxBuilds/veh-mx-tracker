#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import threading
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import webbrowser
import shutil
from collections import Counter, defaultdict

APP_NAME = "Veh Mx Tracker"
APP_ID = "veh-mx-tracker"


def user_config_dir() -> Path:
    """Return the app-owned config/data directory for this platform.

    Linux keeps the original XDG-style location. Windows uses the standard
    per-user local app-data folder, with a one-time copy from the older
    home/.config location if that legacy folder exists.
    """
    legacy = Path.home() / ".config" / APP_ID
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            native = Path(base) / APP_ID
            if legacy.exists() and not native.exists():
                try:
                    native.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(legacy, native)
                except Exception:
                    return legacy
            return native
    return legacy


def default_export_dir() -> Path:
    if os.name == "nt":
        documents = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
        return documents / "MaxxBuilds" / APP_ID / "veh-mx-exports"
    return Path.home() / "Desktop" / "MaxxBuilds" / APP_ID / "veh-mx-exports"


CONFIG_DIR = user_config_dir()
DB_PATH = CONFIG_DIR / "vehicles.sqlite3"
EXPORT_DIR = default_export_dir()
NHTSA_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"
NHTSA_RECALL_BASE = "https://api.nhtsa.gov/recalls/recallsByVehicle"
NHTSA_COMPLAINT_BASE = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
NHTSA_PRODUCTS_BASE = "https://api.nhtsa.gov/products/vehicle"
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
TRANSLITERATION = {**{str(i): i for i in range(10)}, "A":1,"B":2,"C":3,"D":4,"E":5,"F":6,"G":7,"H":8,"J":1,"K":2,"L":3,"M":4,"N":5,"P":7,"R":9,"S":2,"T":3,"U":4,"V":5,"W":6,"X":7,"Y":8,"Z":9}
WEIGHTS = [8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2]
DEFAULT_LINKS = [
    ("RockAuto", "https://www.rockauto.com/"),
    ("AutoZone", "https://www.autozone.com/"),
    ("O'Reilly Auto Parts", "https://www.oreillyauto.com/"),
    ("Advance Auto Parts", "https://shop.advanceautoparts.com/"),
    ("NAPA Auto Parts", "https://www.napaonline.com/"),
    ("eBay Motors", "https://www.ebay.com/b/Auto-Parts-and-Vehicles/6000/bn_1865334"),
    ("NHTSA recalls", "https://www.nhtsa.gov/recalls"),
    ("NHTSA vehicle search", "https://www.nhtsa.gov/vehicle"),
]
DEFAULT_SETTINGS = {
    "theme": "blue",
    "nhtsa_vpic_base": NHTSA_BASE,
    "nhtsa_recall_base": NHTSA_RECALL_BASE,
    "nhtsa_complaint_base": NHTSA_COMPLAINT_BASE,
    "nhtsa_products_base": NHTSA_PRODUCTS_BASE,
    "auto_refresh_nhtsa": "1",
    "open_fullscreen": "1",
}
THEMES = {
    "blue": {"bg":"#08131d", "card":"#122436", "panel":"#07111b", "fg":"#eaf6ff", "accent":"#55c7ff", "select":"#0f6791"},
    "green": {"bg":"#07150d", "card":"#12281a", "panel":"#061109", "fg":"#eaffef", "accent":"#54ff9f", "select":"#16834b"},
    "amber": {"bg":"#171006", "card":"#2b2110", "panel":"#120c04", "fg":"#fff4dd", "accent":"#ffb84d", "select":"#9a6518"},
    "gray": {"bg":"#101418", "card":"#202830", "panel":"#0b0f13", "fg":"#eef3f7", "accent":"#b8d7ff", "select":"#485766"},
}


ACTIVE_SETTINGS = DEFAULT_SETTINGS.copy()


def setting_url(key: str, default: str) -> str:
    return (ACTIVE_SETTINGS.get(key) or default).rstrip("/")


def nowstamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
MONTH_ALIASES = {m.lower(): m for m in MONTHS}
STRICT_DATE_RE = re.compile(r"^(\d{2})\s+([A-Za-z]{3})\s+(\d{4})$")
DATE_INPUT_KEYS = {"service_date", "service_start_date", "service_end_date", "work_date", "next_due", "date_ordered", "start", "end"}
DATE_INPUT_LABELS = {
    "service_date": "Service date",
    "service_start_date": "Service start date",
    "service_end_date": "Service end date",
    "work_date": "Work date",
    "next_due": "Next due",
    "date_ordered": "Date ordered",
    "start": "Start date",
    "end": "End date",
}


def normalize_date_input(value: str, label: str = "Date", required: bool = True) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(f"{label} is required and must use DD MMM YYYY format, for example 30 May 2026.")
        return ""
    match = STRICT_DATE_RE.fullmatch(text)
    if not match:
        raise ValueError(f"{label} must use DD MMM YYYY format, for example 30 May 2026. Other formats such as YYYY-MM-DD are rejected.")
    day_text, month_text, year_text = match.groups()
    month = MONTH_ALIASES.get(month_text.lower())
    if not month:
        raise ValueError(f"{label} must use a three-letter English month abbreviation, for example 30 May 2026.")
    try:
        parsed = datetime(int(year_text), MONTHS[month], int(day_text))
    except ValueError as exc:
        raise ValueError(f"{label} is not a real calendar date: {text}.") from exc
    return parsed.strftime("%d %b %Y")


def normalize_optional_date(value: str, label: str = "Date") -> str:
    return normalize_date_input(value, label, required=False)


def migrate_date_text(value: str, required: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%Y-%m-%d %H:%M", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:16] if fmt == "%Y-%m-%d %H:%M" else text[:10] if fmt == "%Y-%m-%d" else text, fmt).strftime("%d %b %Y")
        except ValueError:
            pass
    return normalize_date_input(text, "Date", required=required)


def date_sort_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.strptime(migrate_date_text(text), "%d %b %Y").strftime("%Y-%m-%d")
    except Exception:
        return text


def today_date() -> str:
    return datetime.now().strftime("%d %b %Y")


def normalize_url_text(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def dashboard_part_names(parts_text: str):
    """Yield real part/material names from the free-form maintenance parts field.

    Demo records may include itemized pricing plus summary text such as
    "Parts/materials subtotal" and "Labor reference". The dashboard's
    Most Used Parts list should count only actual parts/materials, not those
    accounting summary lines.
    """
    for raw_item in re.split(r"[;\n]+", parts_text or ""):
        item = raw_item.strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered.startswith((
            "parts/materials subtotal",
            "parts subtotal",
            "materials subtotal",
            "labor reference",
        )):
            continue
        if re.fullmatch(r"(?:hr|hrs|hours?)\s*=\s*\$?[\d,.]+", lowered):
            continue
        if re.search(r"@\s*\$0(?:\.00)?\s*=\s*\$0(?:\.00)?", item, flags=re.IGNORECASE):
            continue
        item = re.sub(r"\s+x\d+(?:\.\d+)?\s*@\s*\$[\d,.]+\s*=\s*\$[\d,.]+.*$", "", item, flags=re.IGNORECASE).strip()
        item = re.sub(r"\s*@\s*\$[\d,.]+(?:\s*=\s*\$[\d,.]+)?\s*$", "", item, flags=re.IGNORECASE).strip()
        if item and item.lower() not in {"parts", "labor", "labor reference"}:
            yield item


def http_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return json.loads(resp.read().decode(charset, errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"count": 0, "message": "NHTSA endpoint returned 404 for this vehicle/query.", "results": [], "Results": []}
        raise


def vin_check_digit(vin: str) -> str:
    total = sum(TRANSLITERATION[ch] * wt for ch, wt in zip(vin, WEIGHTS))
    rem = total % 11
    return "X" if rem == 10 else str(rem)


def validate_vin(vin: str) -> tuple[bool, str]:
    vin = vin.strip().upper()
    if len(vin) != 17:
        return False, "VIN must be exactly 17 characters."
    if not VIN_RE.match(vin):
        return False, "VIN contains invalid characters. VINs do not use I, O, or Q."
    expected = vin_check_digit(vin)
    if vin[8] != expected:
        return False, f"VIN check digit mismatch. Expected {expected}, found {vin[8]}."
    return True, "VIN format and check digit look valid."


def compact(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"null", "not applicable", "0 - vin decoded clean. check digit (9th position) is correct"}:
        return ""
    return s


def decode_vin(vin: str) -> dict[str, str]:
    url = f"{setting_url('nhtsa_vpic_base', NHTSA_BASE)}/DecodeVinValuesExtended/{urllib.parse.quote(vin)}?format=json"
    data = http_json(url)
    rows = data.get("Results") or []
    if not rows:
        raise RuntimeError("NHTSA returned no decode results.")
    return {k: compact(v) for k, v in rows[0].items() if compact(v)}


def nhtsa_recalls(year: str, make: str, model: str) -> list[dict]:
    qs = urllib.parse.urlencode({"modelYear": year, "make": make, "model": model})
    data = http_json(f"{setting_url('nhtsa_recall_base', NHTSA_RECALL_BASE)}?{qs}")
    return data.get("results") or data.get("Results") or []


def nhtsa_complaints(year: str, make: str, model: str) -> list[dict]:
    qs = urllib.parse.urlencode({"modelYear": year, "make": make, "model": model})
    data = http_json(f"{setting_url('nhtsa_complaint_base', NHTSA_COMPLAINT_BASE)}?{qs}")
    return data.get("results") or data.get("Results") or []


def nhtsa_tsbs(year: str, make: str, model: str) -> list[dict]:
    # NHTSA Products API exposes model availability for TSB issue type. It may not return bulletin summaries.
    qs = urllib.parse.urlencode({"modelYear": year, "make": make, "issueType": "t"})
    data = http_json(f"{setting_url('nhtsa_products_base', NHTSA_PRODUCTS_BASE)}/models?{qs}")
    rows = data.get("results") or data.get("Results") or []
    model_norm = (model or "").strip().upper()
    matches = []
    for row in rows:
        row_model = (row.get("model") or row.get("Model") or "").strip().upper()
        if row_model == model_norm or model_norm in row_model or row_model in model_norm:
            matches.append(row)
    return matches


class Store:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.init_db()

    def init_db(self):
        cur = self.db.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS vehicles (
          id INTEGER PRIMARY KEY,
          vin TEXT UNIQUE NOT NULL,
          nickname TEXT DEFAULT '',
          year TEXT DEFAULT '', make TEXT DEFAULT '', model TEXT DEFAULT '', trim TEXT DEFAULT '',
          engine TEXT DEFAULT '', body TEXT DEFAULT '', raw_json TEXT DEFAULT '{}', public_json TEXT DEFAULT '{}',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
          id INTEGER PRIMARY KEY, vehicle_id INTEGER NOT NULL, created_at TEXT NOT NULL, note TEXT NOT NULL,
          FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS maintenance (
          id INTEGER PRIMARY KEY, vehicle_id INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, service_date TEXT NOT NULL,
          service_start_date TEXT DEFAULT '', service_end_date TEXT DEFAULT '',
          mileage TEXT DEFAULT '', hours TEXT DEFAULT '', category TEXT DEFAULT '', description TEXT NOT NULL,
          next_due TEXT DEFAULT '',
          FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS technicians (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, rank TEXT DEFAULT '', labor_rate REAL DEFAULT 0, active INTEGER DEFAULT 1,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS maintenance_parts (
          id INTEGER PRIMARY KEY, maintenance_id INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          part_name TEXT NOT NULL, part_number TEXT DEFAULT '', supplier TEXT DEFAULT '', date_ordered TEXT DEFAULT '',
          quantity REAL DEFAULT 1, unit_cost REAL DEFAULT 0, total_cost REAL DEFAULT 0,
          technician_id INTEGER, technician_name TEXT DEFAULT '', technician_rank TEXT DEFAULT '', technician_labor_rate REAL DEFAULT 0,
          labor_hours REAL DEFAULT 0, labor_value REAL DEFAULT 0, notes TEXT DEFAULT '',
          FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
          FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS work_items (
          id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, work_date TEXT NOT NULL,
          title TEXT NOT NULL, category TEXT DEFAULT '', description TEXT NOT NULL, parts TEXT DEFAULT '', vendor TEXT DEFAULT '',
          cost REAL DEFAULT 0, labor_hours REAL DEFAULT 0, hours TEXT DEFAULT '', notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS profile (
          id INTEGER PRIMARY KEY CHECK(id=1), name TEXT DEFAULT '', rank TEXT DEFAULT '', labor_cost REAL DEFAULT 0, updated_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS links (
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL, sort_order INTEGER DEFAULT 0, user_added INTEGER DEFAULT 0,
          contact_name TEXT DEFAULT '', contact_title TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '', notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS app_state (
          key TEXT PRIMARY KEY, value TEXT DEFAULT ''
        );
        """)
        link_cols = {r[1] for r in cur.execute("PRAGMA table_info(links)").fetchall()}
        for col in ["contact_name", "contact_title", "email", "phone", "address", "notes"]:
            if col not in link_cols:
                cur.execute(f"ALTER TABLE links ADD COLUMN {col} TEXT DEFAULT ''")
        vehicle_cols = {r[1] for r in cur.execute("PRAGMA table_info(vehicles)").fetchall()}
        if "public_json" not in vehicle_cols:
            cur.execute("ALTER TABLE vehicles ADD COLUMN public_json TEXT DEFAULT '{}'")
        cols = {r[1] for r in cur.execute("PRAGMA table_info(maintenance)").fetchall()}
        if "updated_at" not in cols:
            cur.execute("ALTER TABLE maintenance ADD COLUMN updated_at TEXT DEFAULT ''")
            cur.execute("UPDATE maintenance SET updated_at=created_at WHERE updated_at='' OR updated_at IS NULL")
        if "service_start_date" not in cols:
            cur.execute("ALTER TABLE maintenance ADD COLUMN service_start_date TEXT DEFAULT ''")
        if "service_end_date" not in cols:
            cur.execute("ALTER TABLE maintenance ADD COLUMN service_end_date TEXT DEFAULT ''")
        for row in cur.execute("SELECT id, service_date, service_start_date, service_end_date, next_due FROM maintenance").fetchall():
            start = migrate_date_text(row["service_start_date"] or row["service_date"], required=True)
            end = migrate_date_text(row["service_end_date"], required=False)
            due = migrate_date_text(row["next_due"], required=False)
            cur.execute("UPDATE maintenance SET service_date=?, service_start_date=?, service_end_date=?, next_due=? WHERE id=?", (start, start, end, due, row["id"]))
        cur.execute("INSERT OR IGNORE INTO profile(id,name,rank,labor_cost,updated_at) VALUES(1,'','',0,'')")
        cur.execute("""CREATE TABLE IF NOT EXISTS technicians (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, rank TEXT DEFAULT '', labor_rate REAL DEFAULT 0, active INTEGER DEFAULT 1,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        ts = nowstamp()
        if cur.execute("SELECT COUNT(*) FROM technicians").fetchone()[0] == 0:
            prof = cur.execute("SELECT * FROM profile WHERE id=1").fetchone()
            name = str((prof["name"] if prof else "") or "").strip() or "Default Technician"
            rank = str((prof["rank"] if prof else "") or "").strip()
            try:
                rate = float((prof["labor_cost"] if prof else 0) or 0)
            except (TypeError, ValueError):
                rate = 0.0
            cur.execute("INSERT INTO technicians(name,rank,labor_rate,active,created_at,updated_at) VALUES(?,?,?,?,?,?)", (name, rank, rate, 1, ts, ts))
            cur.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES('default_technician_id', ?)", (str(cur.lastrowid),))
        default_tech = cur.execute("SELECT * FROM technicians ORDER BY active DESC,id LIMIT 1").fetchone()
        default_tech_id = default_tech["id"] if default_tech else None
        default_name = default_tech["name"] if default_tech else "Default Technician"
        default_rank = default_tech["rank"] if default_tech else ""
        default_rate = float(default_tech["labor_rate"] if default_tech else 0)
        part_cols = {r[1] for r in cur.execute("PRAGMA table_info(maintenance_parts)").fetchall()}
        for col, ddl in [
            ("technician_id", "ALTER TABLE maintenance_parts ADD COLUMN technician_id INTEGER"),
            ("technician_name", "ALTER TABLE maintenance_parts ADD COLUMN technician_name TEXT DEFAULT ''"),
            ("technician_rank", "ALTER TABLE maintenance_parts ADD COLUMN technician_rank TEXT DEFAULT ''"),
            ("technician_labor_rate", "ALTER TABLE maintenance_parts ADD COLUMN technician_labor_rate REAL DEFAULT 0"),
            ("labor_hours", "ALTER TABLE maintenance_parts ADD COLUMN labor_hours REAL DEFAULT 0"),
            ("labor_value", "ALTER TABLE maintenance_parts ADD COLUMN labor_value REAL DEFAULT 0"),
        ]:
            if col not in part_cols:
                cur.execute(ddl)
        cur.execute("""UPDATE maintenance_parts
                       SET technician_id=COALESCE(technician_id, ?),
                           technician_name=CASE WHEN technician_name IS NULL OR technician_name='' THEN ? ELSE technician_name END,
                           technician_rank=CASE WHEN technician_rank IS NULL OR technician_rank='' THEN ? ELSE technician_rank END,
                           technician_labor_rate=CASE WHEN technician_labor_rate IS NULL OR technician_labor_rate=0 THEN ? ELSE technician_labor_rate END,
                           labor_hours=COALESCE(labor_hours, 0),
                           labor_value=ROUND(COALESCE(labor_hours,0) * COALESCE(technician_labor_rate,0), 2)
                       WHERE technician_id IS NULL OR technician_name='' OR labor_value IS NULL""", (default_tech_id, default_name, default_rank, default_rate))
        cols = {r[1] for r in cur.execute("PRAGMA table_info(maintenance)").fetchall()}
        if "labor_hours" in cols:
            for row in cur.execute("SELECT id, service_date, service_start_date, labor_hours FROM maintenance WHERE COALESCE(labor_hours,0) > 0").fetchall():
                exists = cur.execute("SELECT 1 FROM maintenance_parts WHERE maintenance_id=? AND part_name='Legacy labor' AND notes='Migrated from parent maintenance labor hours.'", (row["id"],)).fetchone()
                if exists:
                    continue
                labor_hours = float(row["labor_hours"] or 0)
                labor_value = round(labor_hours * default_rate, 2)
                cur.execute("""INSERT INTO maintenance_parts(maintenance_id,created_at,updated_at,part_name,part_number,supplier,date_ordered,quantity,unit_cost,total_cost,technician_id,technician_name,technician_rank,technician_labor_rate,labor_hours,labor_value,notes)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (row["id"], ts, ts, "Legacy labor", "", "", row["service_start_date"] or row["service_date"], 1, 0, 0, default_tech_id, default_name, default_rank, default_rate, labor_hours, labor_value, "Migrated from parent maintenance labor hours."))
        cols = {r[1] for r in cur.execute("PRAGMA table_info(maintenance)").fetchall()}
        if "parts" in cols or "cost" in cols or "vendor" in cols:
            select_fields = ["id", "service_date", "service_start_date"]
            select_fields.append("parts" if "parts" in cols else "'' AS parts")
            select_fields.append("vendor" if "vendor" in cols else "'' AS vendor")
            select_fields.append("cost" if "cost" in cols else "0 AS cost")
            for row in cur.execute(f"SELECT {', '.join(select_fields)} FROM maintenance").fetchall():
                parts_text = str(row["parts"] or "").strip()
                supplier = str(row["vendor"] or "").strip()
                try:
                    cost = float(row["cost"] or 0)
                except (TypeError, ValueError):
                    cost = 0.0
                if not parts_text and not supplier and cost <= 0:
                    continue
                exists = cur.execute("""SELECT 1 FROM maintenance_parts
                                      WHERE maintenance_id=? AND notes LIKE 'Migrated from parent maintenance parts/cost/vendor.%'""", (row["id"],)).fetchone()
                if exists:
                    continue
                migrated_names = list(dashboard_part_names(parts_text))
                part_name = migrated_names[0] if migrated_names else (parts_text[:120] if parts_text else "Legacy parts/materials")
                notes = "Migrated from parent maintenance parts/cost/vendor."
                if parts_text:
                    notes += f" Original parts: {parts_text}"
                total_cost = round(cost, 2) if cost > 0 else 0.0
                cur.execute("""INSERT INTO maintenance_parts(maintenance_id,created_at,updated_at,part_name,part_number,supplier,date_ordered,quantity,unit_cost,total_cost,technician_id,technician_name,technician_rank,technician_labor_rate,labor_hours,labor_value,notes)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (row["id"], ts, ts, part_name, "", supplier, row["service_start_date"] or row["service_date"], 1, total_cost, total_cost, default_tech_id, default_name, default_rank, default_rate, 0, 0, notes))
        if "parts" in cols or "cost" in cols or "vendor" in cols or "labor_hours" in cols:
            cur.execute("CREATE TEMP TABLE IF NOT EXISTS maintenance_parts_keep AS SELECT * FROM maintenance_parts")
            cur.execute("ALTER TABLE maintenance RENAME TO maintenance_old")
            cur.execute("""CREATE TABLE maintenance (
              id INTEGER PRIMARY KEY, vehicle_id INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, service_date TEXT NOT NULL,
              service_start_date TEXT DEFAULT '', service_end_date TEXT DEFAULT '',
              mileage TEXT DEFAULT '', hours TEXT DEFAULT '', category TEXT DEFAULT '', description TEXT NOT NULL,
              next_due TEXT DEFAULT '',
              FOREIGN KEY(vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
            )""")
            cur.execute("""INSERT INTO maintenance(id,vehicle_id,created_at,updated_at,service_date,service_start_date,service_end_date,mileage,hours,category,description,next_due)
                           SELECT id,vehicle_id,created_at,updated_at,service_date,service_start_date,service_end_date,mileage,hours,category,description,next_due FROM maintenance_old""")
            cur.execute("DROP TABLE maintenance_old")
        fk_targets = {r[2] for r in cur.execute("PRAGMA foreign_key_list(maintenance_parts)").fetchall()}
        if fk_targets and "maintenance" not in fk_targets:
            cur.execute("ALTER TABLE maintenance_parts RENAME TO maintenance_parts_old")
            cur.execute("""CREATE TABLE maintenance_parts (
              id INTEGER PRIMARY KEY, maintenance_id INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              part_name TEXT NOT NULL, part_number TEXT DEFAULT '', supplier TEXT DEFAULT '', date_ordered TEXT DEFAULT '',
              quantity REAL DEFAULT 1, unit_cost REAL DEFAULT 0, total_cost REAL DEFAULT 0,
              technician_id INTEGER, technician_name TEXT DEFAULT '', technician_rank TEXT DEFAULT '', technician_labor_rate REAL DEFAULT 0,
              labor_hours REAL DEFAULT 0, labor_value REAL DEFAULT 0, notes TEXT DEFAULT '',
              FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
              FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE SET NULL
            )""")
            cur.execute("""INSERT OR IGNORE INTO maintenance_parts(id,maintenance_id,created_at,updated_at,part_name,part_number,supplier,date_ordered,quantity,unit_cost,total_cost,technician_id,technician_name,technician_rank,technician_labor_rate,labor_hours,labor_value,notes)
                           SELECT id,maintenance_id,created_at,updated_at,part_name,part_number,supplier,date_ordered,quantity,unit_cost,total_cost,technician_id,technician_name,technician_rank,technician_labor_rate,labor_hours,labor_value,notes FROM maintenance_parts_old
                           WHERE maintenance_id IN (SELECT id FROM maintenance)""")
            cur.execute("DROP TABLE maintenance_parts_old")
        if cur.execute("SELECT name FROM sqlite_temp_master WHERE type='table' AND name='maintenance_parts_keep'").fetchone():
            if cur.execute("SELECT COUNT(*) FROM maintenance_parts").fetchone()[0] == 0:
                cur.execute("""INSERT OR IGNORE INTO maintenance_parts(id,maintenance_id,created_at,updated_at,part_name,part_number,supplier,date_ordered,quantity,unit_cost,total_cost,technician_id,technician_name,technician_rank,technician_labor_rate,labor_hours,labor_value,notes)
                               SELECT id,maintenance_id,created_at,updated_at,part_name,part_number,supplier,date_ordered,quantity,unit_cost,total_cost,technician_id,technician_name,technician_rank,technician_labor_rate,labor_hours,labor_value,notes FROM maintenance_parts_keep
                               WHERE maintenance_id IN (SELECT id FROM maintenance)""")
            cur.execute("DROP TABLE maintenance_parts_keep")
        for row in cur.execute("SELECT id, date_ordered FROM maintenance_parts").fetchall():
            ordered = migrate_date_text(row["date_ordered"], required=False)
            if ordered != (row["date_ordered"] or ""):
                cur.execute("UPDATE maintenance_parts SET date_ordered=? WHERE id=?", (ordered, row["id"]))
        for row in cur.execute("SELECT id, work_date FROM work_items").fetchall():
            work_date = migrate_date_text(row["work_date"], required=True)
            if work_date != (row["work_date"] or ""):
                cur.execute("UPDATE work_items SET work_date=? WHERE id=?", (work_date, row["id"]))
        if cur.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0:
            cur.executemany("INSERT INTO links(title,url,sort_order,user_added) VALUES(?,?,?,0)", [(t,u,i) for i,(t,u) in enumerate(DEFAULT_LINKS)])
        self.db.commit()

    def vehicles(self):
        return self.db.execute("SELECT * FROM vehicles ORDER BY COALESCE(NULLIF(nickname,''), make||' '||model||' '||vin)").fetchall()

    def search_vehicles(self, term: str):
        term = (term or "").strip()
        if not term:
            return self.vehicles()
        like = f"%{term}%"
        return self.db.execute("""SELECT * FROM vehicles
            WHERE vin LIKE ? OR nickname LIKE ? OR year LIKE ? OR make LIKE ? OR model LIKE ? OR trim LIKE ? OR engine LIKE ? OR body LIKE ?
            ORDER BY COALESCE(NULLIF(nickname,''), make||' '||model||' '||vin)""", (like,)*8).fetchall()

    def get_vehicle(self, vid: int):
        return self.db.execute("SELECT * FROM vehicles WHERE id=?", (vid,)).fetchone()

    def save_vehicle(self, vin: str, decoded: dict[str, str], nickname: str = "") -> int:
        # No fixed vehicle limit; SQLite storage is limited only by available disk space.
        vals = {
            "year": decoded.get("ModelYear", ""), "make": decoded.get("Make", ""), "model": decoded.get("Model", ""),
            "trim": decoded.get("Trim", ""), "engine": decoded.get("EngineModel") or decoded.get("DisplacementL", ""),
            "body": decoded.get("BodyClass", ""), "raw_json": json.dumps(decoded, indent=2),
        }
        ts = nowstamp()
        row = self.db.execute("SELECT id,nickname FROM vehicles WHERE vin=?", (vin,)).fetchone()
        if row:
            nick = nickname if nickname else row["nickname"]
            self.db.execute("""UPDATE vehicles SET nickname=?, year=?, make=?, model=?, trim=?, engine=?, body=?, raw_json=?, updated_at=? WHERE id=?""", (nick, vals["year"], vals["make"], vals["model"], vals["trim"], vals["engine"], vals["body"], vals["raw_json"], ts, row["id"]))
            self.db.commit(); return row["id"]
        cur = self.db.execute("""INSERT INTO vehicles(vin,nickname,year,make,model,trim,engine,body,raw_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (vin,nickname,vals["year"],vals["make"],vals["model"],vals["trim"],vals["engine"],vals["body"],vals["raw_json"],ts,ts))
        self.db.commit(); return cur.lastrowid

    def save_manual_vehicle(self, data: dict) -> int:
        # No fixed vehicle limit; SQLite storage is limited only by available disk space.
        ts = nowstamp()
        internal_vin = f"NO-VIN-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        raw = {"ManualEntry": "Yes", "NoVIN": "Yes"}
        cur = self.db.execute("""INSERT INTO vehicles(vin,nickname,year,make,model,trim,engine,body,raw_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (internal_vin, data.get("nickname",""), data.get("year",""), data.get("make",""), data.get("model",""), data.get("trim",""), data.get("engine",""), data.get("body",""), json.dumps(raw), ts, ts))
        self.db.commit(); return cur.lastrowid

    def update_nickname(self, vid: int, nickname: str):
        self.db.execute("UPDATE vehicles SET nickname=?, updated_at=? WHERE id=?", (nickname, nowstamp(), vid)); self.db.commit()

    def save_vehicle_public_info(self, vid: int, decoded: dict, recalls: list, complaints: list, tsbs: list):
        cached_at = nowstamp()
        payload = {
            "cached_at": cached_at,
            "source": "NHTSA public APIs",
            "decoded": decoded or {},
            "recalls": recalls or [],
            "complaints": complaints or [],
            "tsbs": tsbs or [],
            "counts": {"recalls": len(recalls or []), "complaints": len(complaints or []), "tsbs": len(tsbs or [])},
        }
        self.db.execute("UPDATE vehicles SET raw_json=?, public_json=?, updated_at=? WHERE id=?", (json.dumps(decoded or {}, indent=2), json.dumps(payload, indent=2), cached_at, vid))
        self.db.commit()

    def cached_vehicle_public_info(self, vid: int):
        row = self.get_vehicle(vid)
        if not row:
            return None
        try:
            data = json.loads(row["public_json"] or "{}")
            return data if data else None
        except Exception:
            return None

    def update_vehicle_info(self, vid: int, data: dict):
        current = self.get_vehicle(vid)
        vin = (data.get("vin") or "").strip().upper()
        raw = json.loads(current["raw_json"] or "{}") if current else {}
        if vin:
            ok, msg = validate_vin(vin)
            if not ok:
                raise RuntimeError(msg)
            try:
                decoded = decode_vin(vin)
                raw.update(decoded)
                data["year"] = data.get("year") or decoded.get("ModelYear", "")
                data["make"] = data.get("make") or decoded.get("Make", "")
                data["model"] = data.get("model") or decoded.get("Model", "")
                data["trim"] = data.get("trim") or decoded.get("Trim", "")
                data["engine"] = data.get("engine") or decoded.get("EngineModel") or decoded.get("DisplacementL", "")
                data["body"] = data.get("body") or decoded.get("BodyClass", "")
            except Exception:
                # Validation passed; if public decode is unavailable, still allow the saved VIN and manual fields.
                raw.update({"ManualDecodeNote": "VIN saved; public decode unavailable during edit."})
        else:
            vin = current["vin"] if current and str(current["vin"]).startswith("NO-VIN-") else f"NO-VIN-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            raw.update({"ManualEntry": "Yes", "NoVIN": "Yes"})
        self.db.execute("""UPDATE vehicles SET vin=?, nickname=?, year=?, make=?, model=?, trim=?, engine=?, body=?, raw_json=?, updated_at=? WHERE id=?""",
            (vin, data.get("nickname", ""), data.get("year", ""), data.get("make", ""), data.get("model", ""), data.get("trim", ""), data.get("engine", ""), data.get("body", ""), json.dumps(raw, indent=2), nowstamp(), vid))
        self.db.commit()

    def delete_vehicle(self, vid: int):
        self.db.execute("DELETE FROM vehicles WHERE id=?", (vid,)); self.db.commit()

    def add_note(self, vid: int, note: str):
        self.db.execute("INSERT INTO notes(vehicle_id,created_at,note) VALUES(?,?,?)", (vid, nowstamp(), note)); self.db.commit()

    def notes(self, vid: int):
        return self.db.execute("SELECT * FROM notes WHERE vehicle_id=? ORDER BY created_at DESC,id DESC", (vid,)).fetchall()

    def update_note(self, nid: int, note: str):
        self.db.execute("UPDATE notes SET note=? WHERE id=?", (note, nid)); self.db.commit()

    def delete_note(self, nid: int):
        self.db.execute("DELETE FROM notes WHERE id=?", (nid,)); self.db.commit()

    def _mx_values(self, data: dict):
        start = normalize_date_input(data.get("service_start_date") or data.get("service_date"), "Service start date", required=True)
        return {
            "service_start_date": start,
            "service_end_date": normalize_optional_date(data.get("service_end_date"), "Service end date"),
            "mileage": data.get("mileage", ""),
            "hours": data.get("hours", ""),
            "category": data.get("category", ""),
            "description": data.get("description", ""),
            "next_due": normalize_optional_date(data.get("next_due", ""), "Next due"),
        }

    def add_mx(self, vid: int, data: dict):
        vals = self._mx_values(data)
        ts = nowstamp()
        cur = self.db.execute("""INSERT INTO maintenance(vehicle_id,created_at,updated_at,service_date,service_start_date,service_end_date,mileage,hours,category,description,next_due)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (vid, ts, ts, vals["service_start_date"], vals["service_start_date"], vals["service_end_date"], vals["mileage"], vals["hours"], vals["category"], vals["description"], vals["next_due"]))
        self.db.commit()
        return cur.lastrowid

    def update_mx(self, mid: int, data: dict):
        vals = self._mx_values(data)
        self.db.execute("""UPDATE maintenance SET updated_at=?, service_date=?, service_start_date=?, service_end_date=?, mileage=?, hours=?, category=?, description=?, next_due=? WHERE id=?""",
            (nowstamp(), vals["service_start_date"], vals["service_start_date"], vals["service_end_date"], vals["mileage"], vals["hours"], vals["category"], vals["description"], vals["next_due"], mid))
        self.db.commit()

    def maintenance(self, vid: int):
        rows = self.db.execute("SELECT * FROM maintenance WHERE vehicle_id=?", (vid,)).fetchall()
        return sorted(rows, key=lambda r: (date_sort_key(r["service_start_date"] or r["service_date"]), r["id"]), reverse=True)

    def delete_mx(self, mid: int):
        self.db.execute("DELETE FROM maintenance WHERE id=?", (mid,)); self.db.commit()

    def technicians(self, include_inactive: bool = True):
        where = "" if include_inactive else " WHERE active=1"
        return self.db.execute("SELECT * FROM technicians" + where + " ORDER BY active DESC, name COLLATE NOCASE, id").fetchall()

    def get_technician(self, technician_id):
        try:
            tid = int(technician_id)
        except (TypeError, ValueError):
            return None
        return self.db.execute("SELECT * FROM technicians WHERE id=?", (tid,)).fetchone()

    def default_technician(self):
        raw = self.load_state("default_technician_id", "")
        tech = self.get_technician(raw) if raw else None
        if tech and int(tech["active"] or 0):
            return tech
        return self.db.execute("SELECT * FROM technicians WHERE active=1 ORDER BY id LIMIT 1").fetchone() or self.db.execute("SELECT * FROM technicians ORDER BY id LIMIT 1").fetchone()

    def set_default_technician(self, technician_id: int):
        tech = self.get_technician(technician_id)
        if not tech:
            raise ValueError("Select a valid technician.")
        self.save_state("default_technician_id", str(tech["id"]))

    def add_technician(self, data: dict):
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Technician name is required.")
        try:
            rate = float(data.get("labor_rate") or data.get("labor_cost") or 0)
        except (TypeError, ValueError):
            rate = 0.0
        active = 1 if str(data.get("active", "1")).strip().lower() not in {"0", "no", "false", "inactive"} else 0
        ts = nowstamp()
        cur = self.db.execute("INSERT INTO technicians(name,rank,labor_rate,active,created_at,updated_at) VALUES(?,?,?,?,?,?)", (name, str(data.get("rank") or "").strip(), rate, active, ts, ts))
        self.db.commit()
        if not self.load_state("default_technician_id", ""):
            self.set_default_technician(cur.lastrowid)
        return cur.lastrowid

    def update_technician(self, technician_id: int, data: dict):
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Technician name is required.")
        try:
            rate = float(data.get("labor_rate") or data.get("labor_cost") or 0)
        except (TypeError, ValueError):
            rate = 0.0
        active = 1 if str(data.get("active", "1")).strip().lower() not in {"0", "no", "false", "inactive"} else 0
        self.db.execute("UPDATE technicians SET name=?, rank=?, labor_rate=?, active=?, updated_at=? WHERE id=?", (name, str(data.get("rank") or "").strip(), rate, active, nowstamp(), technician_id))
        self.db.commit()

    def technician_in_use(self, technician_id: int) -> bool:
        return bool(self.db.execute("SELECT 1 FROM maintenance_parts WHERE technician_id=? LIMIT 1", (technician_id,)).fetchone())

    def delete_technician(self, technician_id: int):
        if self.technician_in_use(technician_id):
            raise ValueError("This technician is used by maintenance parts/labor records. Mark inactive instead.")
        self.db.execute("DELETE FROM technicians WHERE id=?", (technician_id,))
        self.db.commit()
        default = self.default_technician()
        if default:
            self.save_state("default_technician_id", str(default["id"]))

    def _part_values(self, data: dict):
        name = str(data.get("part_name") or "").strip()
        if not name:
            raise ValueError("Part name is required.")
        try:
            qty = float(data.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        try:
            unit_cost = float(data.get("unit_cost") or 0)
        except (TypeError, ValueError):
            unit_cost = 0.0
        unit_cost = round(unit_cost, 2)
        total_cost = round(qty * unit_cost, 2)
        try:
            labor_hours = float(data.get("labor_hours") or 0)
        except (TypeError, ValueError):
            labor_hours = 0.0
        tech = self.get_technician(data.get("technician_id")) if data.get("technician_id") else self.default_technician()
        if tech:
            technician_id = tech["id"]
            technician_name = tech["name"]
            technician_rank = tech["rank"]
            technician_labor_rate = float(tech["labor_rate"] or 0)
        else:
            technician_id = None
            technician_name = str(data.get("technician_name") or "").strip()
            technician_rank = str(data.get("technician_rank") or "").strip()
            try:
                technician_labor_rate = float(data.get("technician_labor_rate") or 0)
            except (TypeError, ValueError):
                technician_labor_rate = 0.0
        labor_value = round(labor_hours * technician_labor_rate, 2)
        return {
            "part_name": name,
            "part_number": str(data.get("part_number") or "").strip(),
            "supplier": str(data.get("supplier") or "").strip(),
            "date_ordered": normalize_optional_date(data.get("date_ordered"), "Date ordered"),
            "quantity": qty,
            "unit_cost": unit_cost,
            "total_cost": total_cost,
            "technician_id": technician_id,
            "technician_name": technician_name,
            "technician_rank": technician_rank,
            "technician_labor_rate": technician_labor_rate,
            "labor_hours": labor_hours,
            "labor_value": labor_value,
            "notes": str(data.get("notes") or "").strip(),
        }

    def ensure_supplier_source(self, data: dict):
        title = str(data.get("supplier") or data.get("title") or "").strip()
        if not title:
            return
        supplier_data = {
            "title": title,
            "url": normalize_url_text(data.get("supplier_url", "")),
            "contact_name": str(data.get("supplier_contact_name") or "").strip(),
            "contact_title": str(data.get("supplier_contact_title") or "").strip(),
            "email": str(data.get("supplier_email") or "").strip(),
            "phone": str(data.get("supplier_phone") or "").strip(),
            "address": str(data.get("supplier_address") or "").strip(),
            "notes": str(data.get("supplier_notes") or "").strip(),
        }
        existing = self.db.execute("SELECT * FROM links WHERE lower(title)=lower(?)", (title,)).fetchone()
        has_detail = any(supplier_data[k] for k in ("url", "contact_name", "contact_title", "email", "phone", "address", "notes"))
        if existing:
            if has_detail:
                merged = {k: supplier_data[k] or existing[k] for k in ("title", "url", "contact_name", "contact_title", "email", "phone", "address", "notes")}
                self.update_link(existing["id"], merged)
            return
        self.add_link(supplier_data)

    def add_mx_part(self, maintenance_id: int, data: dict):
        vals = self._part_values(data)
        self.ensure_supplier_source(data)
        ts = nowstamp()
        cur = self.db.execute("""INSERT INTO maintenance_parts(maintenance_id,created_at,updated_at,part_name,part_number,supplier,date_ordered,quantity,unit_cost,total_cost,technician_id,technician_name,technician_rank,technician_labor_rate,labor_hours,labor_value,notes)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (maintenance_id, ts, ts, vals["part_name"], vals["part_number"], vals["supplier"], vals["date_ordered"], vals["quantity"], vals["unit_cost"], vals["total_cost"], vals["technician_id"], vals["technician_name"], vals["technician_rank"], vals["technician_labor_rate"], vals["labor_hours"], vals["labor_value"], vals["notes"]))
        self.db.commit()
        return cur.lastrowid

    def update_mx_part(self, part_id: int, data: dict):
        vals = self._part_values(data)
        self.ensure_supplier_source(data)
        self.db.execute("""UPDATE maintenance_parts SET updated_at=?, part_name=?, part_number=?, supplier=?, date_ordered=?, quantity=?, unit_cost=?, total_cost=?, technician_id=?, technician_name=?, technician_rank=?, technician_labor_rate=?, labor_hours=?, labor_value=?, notes=? WHERE id=?""",
            (nowstamp(), vals["part_name"], vals["part_number"], vals["supplier"], vals["date_ordered"], vals["quantity"], vals["unit_cost"], vals["total_cost"], vals["technician_id"], vals["technician_name"], vals["technician_rank"], vals["technician_labor_rate"], vals["labor_hours"], vals["labor_value"], vals["notes"], part_id))
        self.db.commit()

    def delete_mx_part(self, part_id: int):
        self.db.execute("DELETE FROM maintenance_parts WHERE id=?", (part_id,)); self.db.commit()

    def replace_mx_parts(self, maintenance_id: int, parts: list[dict]):
        self.db.execute("DELETE FROM maintenance_parts WHERE maintenance_id=?", (maintenance_id,))
        self.db.commit()
        for part in parts:
            self.add_mx_part(maintenance_id, part)

    def mx_parts(self, maintenance_id: int):
        return self.db.execute("SELECT * FROM maintenance_parts WHERE maintenance_id=? ORDER BY date_ordered DESC,id DESC", (maintenance_id,)).fetchall()

    def mx_parts_total(self, maintenance_id: int) -> float:
        row = self.db.execute("SELECT COALESCE(SUM(total_cost),0) FROM maintenance_parts WHERE maintenance_id=?", (maintenance_id,)).fetchone()
        return round(float(row[0] or 0), 2)

    def structured_parts_for_vehicle(self, vehicle_id: int):
        rows = self.db.execute("""SELECT mp.*, m.service_date, m.service_start_date, m.service_end_date, m.description, m.category, v.nickname, v.vin, v.year, v.make, v.model
                                  FROM maintenance_parts mp
                                  JOIN maintenance m ON m.id=mp.maintenance_id
                                  JOIN vehicles v ON v.id=m.vehicle_id
                                  WHERE v.id=?""", (vehicle_id,)).fetchall()
        return sorted(rows, key=lambda r: (date_sort_key(r["service_start_date"] or r["service_date"]), date_sort_key(r["date_ordered"]), r["id"]), reverse=True)

    def structured_parts_all(self, start: str = "", end: str = ""):
        rows = self.db.execute("""SELECT mp.*, m.service_date, m.service_start_date, m.service_end_date, m.category, m.description, m.mileage, m.hours, v.nickname, v.vin, v.year, v.make, v.model
                                   FROM maintenance_parts mp
                                   JOIN maintenance m ON m.id=mp.maintenance_id
                                   JOIN vehicles v ON v.id=m.vehicle_id""").fetchall()
        s = date_sort_key(start) if start else ""
        e = date_sort_key(end) if end else ""
        filtered = [r for r in rows if (not s or date_sort_key(r["service_start_date"] or r["service_date"]) >= s) and (not e or date_sort_key(r["service_start_date"] or r["service_date"]) <= e)]
        return sorted(filtered, key=lambda r: (date_sort_key(r["service_start_date"] or r["service_date"]), date_sort_key(r["date_ordered"]), r["id"]), reverse=True)

    def export_parts_csv(self, path, start: str = "", end: str = ""):
        rows = self.structured_parts_all(start, end)
        fields = ["maintenance_id", "service_date", "vehicle", "vin", "category", "description", "part_name", "part_number", "supplier", "date_ordered", "quantity", "unit_cost", "total_cost", "technician", "technician_rank", "labor_rate", "labor_hours", "labor_value", "notes"]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for r in rows:
                vehicle = r["nickname"] or " ".join(x for x in [r["year"], r["make"], r["model"]] if x) or r["vin"]
                writer.writerow({
                    "maintenance_id": r["maintenance_id"],
                    "service_date": r["service_date"],
                    "vehicle": vehicle,
                    "vin": "" if str(r["vin"]).startswith("NO-VIN-") else r["vin"],
                    "category": r["category"],
                    "description": r["description"],
                    "part_name": r["part_name"],
                    "part_number": r["part_number"],
                    "supplier": r["supplier"],
                    "date_ordered": r["date_ordered"],
                    "quantity": f"{float(r['quantity'] or 0):.1f}",
                    "unit_cost": f"{float(r['unit_cost'] or 0):.2f}",
                    "total_cost": f"{float(r['total_cost'] or 0):.2f}",
                    "technician": r["technician_name"],
                    "technician_rank": r["technician_rank"],
                    "labor_rate": f"{float(r['technician_labor_rate'] or 0):.2f}",
                    "labor_hours": f"{float(r['labor_hours'] or 0):.2f}",
                    "labor_value": f"{float(r['labor_value'] or 0):.2f}",
                    "notes": r["notes"],
                })
        return path

    def work_items(self):
        return self.db.execute("SELECT * FROM work_items ORDER BY work_date DESC,id DESC").fetchall()

    def _work_values(self, data: dict):
        vals = dict(data)
        vals["work_date"] = normalize_date_input(vals.get("work_date"), "Work date", required=True)
        return vals

    def add_work(self, data: dict):
        data = self._work_values(data)
        ts = nowstamp()
        self.db.execute("""INSERT INTO work_items(created_at,updated_at,work_date,title,category,description,parts,vendor,cost,labor_hours,hours,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ts, ts, data["work_date"], data["title"], data["category"], data["description"], data["parts"], data["vendor"], data["cost"], data["labor_hours"], data["hours"], data["notes"]))
        self.db.commit()

    def update_work(self, wid: int, data: dict):
        data = self._work_values(data)
        self.db.execute("""UPDATE work_items SET updated_at=?, work_date=?, title=?, category=?, description=?, parts=?, vendor=?, cost=?, labor_hours=?, hours=?, notes=? WHERE id=?""",
            (nowstamp(), data["work_date"], data["title"], data["category"], data["description"], data["parts"], data["vendor"], data["cost"], data["labor_hours"], data["hours"], data["notes"], wid))
        self.db.commit()

    def delete_work(self, wid: int):
        self.db.execute("DELETE FROM work_items WHERE id=?", (wid,)); self.db.commit()

    def search_records(self, term: str):
        like = f"%{term}%"
        rows = []
        for r in self.db.execute("""SELECT 'Vehicle MX' AS kind, m.id AS record_id, v.id AS vehicle_id, v.vin, v.nickname, m.service_date AS rec_date, m.description AS text, 0 AS cost, 0 AS labor_hours
                                  FROM maintenance m JOIN vehicles v ON v.id=m.vehicle_id
                                  WHERE v.vin LIKE ? OR v.nickname LIKE ? OR v.make LIKE ? OR v.model LIKE ? OR m.category LIKE ? OR m.description LIKE ?
                                  ORDER BY m.service_date DESC LIMIT 500""", (like,)*6):
            rows.append(dict(r))
        for r in self.db.execute("""SELECT 'Vehicle Part' AS kind, m.id AS record_id, v.id AS vehicle_id, v.vin, v.nickname, m.service_date AS rec_date,
                                         (mp.part_name || CASE WHEN mp.part_number != '' THEN ' #' || mp.part_number ELSE '' END || CASE WHEN mp.supplier != '' THEN ' from ' || mp.supplier ELSE '' END || CASE WHEN mp.technician_name != '' THEN ' by ' || mp.technician_name ELSE '' END) AS text,
                                         (mp.total_cost + mp.labor_value) AS cost, mp.labor_hours AS labor_hours
                                  FROM maintenance_parts mp
                                  JOIN maintenance m ON m.id=mp.maintenance_id
                                  JOIN vehicles v ON v.id=m.vehicle_id
                                  WHERE v.vin LIKE ? OR v.nickname LIKE ? OR v.make LIKE ? OR v.model LIKE ? OR mp.part_name LIKE ? OR mp.part_number LIKE ? OR mp.supplier LIKE ? OR mp.technician_name LIKE ? OR mp.technician_rank LIKE ? OR mp.notes LIKE ?
                                  ORDER BY m.service_date DESC LIMIT 500""", (like,)*10):
            rows.append(dict(r))
        for r in self.db.execute("""SELECT 'Unlinked Work' AS kind, id AS record_id, NULL AS vehicle_id, '' AS vin, title AS nickname, work_date AS rec_date, description AS text, cost, labor_hours
                                  FROM work_items
                                  WHERE title LIKE ? OR category LIKE ? OR description LIKE ? OR parts LIKE ? OR vendor LIKE ? OR notes LIKE ?
                                  ORDER BY work_date DESC LIMIT 500""", (like,)*6):
            rows.append(dict(r))
        for r in self.db.execute("""SELECT 'Note' AS kind, n.id AS record_id, v.id AS vehicle_id, v.vin, v.nickname, n.created_at AS rec_date, n.note AS text, 0 AS cost, 0 AS labor_hours
                                  FROM notes n JOIN vehicles v ON v.id=n.vehicle_id
                                  WHERE v.vin LIKE ? OR v.nickname LIKE ? OR n.note LIKE ?
                                  ORDER BY n.created_at DESC LIMIT 500""", (like, like, like)):
            rows.append(dict(r))
        return sorted(rows, key=lambda x: date_sort_key(x.get("rec_date") or ""), reverse=True)[:500]

    def profile(self):
        return self.db.execute("SELECT * FROM profile WHERE id=1").fetchone()

    def update_profile(self, name: str, rank: str, labor_cost: float):
        self.db.execute("UPDATE profile SET name=?, rank=?, labor_cost=?, updated_at=? WHERE id=1", (name, rank, labor_cost, nowstamp()))
        self.db.commit()

    def profile_incomplete(self):
        return self.default_technician() is None

    def totals(self, start: str = "", end: str = "", vehicle_id=None):
        s = date_sort_key(start) if start else ""
        e = date_sort_key(end) if end else ""
        mx_rows = self.db.execute("SELECT * FROM maintenance" + (" WHERE vehicle_id=?" if vehicle_id else ""), ((vehicle_id,) if vehicle_id else ())).fetchall()
        mx_rows = [r for r in mx_rows if (not s or date_sort_key(r["service_start_date"] or r["service_date"]) >= s) and (not e or date_sort_key(r["service_start_date"] or r["service_date"]) <= e)]
        mx_ids = [r["id"] for r in mx_rows]
        labor_hours = 0.0
        labor_value = 0.0
        parts_cost = 0.0
        if mx_ids:
            q = ",".join("?" for _ in mx_ids)
            row = self.db.execute(f"SELECT COALESCE(SUM(total_cost),0), COALESCE(SUM(labor_hours),0), COALESCE(SUM(labor_value),0) FROM maintenance_parts WHERE maintenance_id IN ({q})", mx_ids).fetchone()
            parts_cost = float(row[0] or 0)
            labor_hours = float(row[1] or 0)
            labor_value = float(row[2] or 0)
        other_direct_cost = 0.0
        count = len(mx_rows)
        if vehicle_id is None:
            work_rows = self.db.execute("SELECT * FROM work_items").fetchall()
            work_rows = [r for r in work_rows if (not s or date_sort_key(r["work_date"]) >= s) and (not e or date_sort_key(r["work_date"]) <= e)]
            labor_hours += sum(float(r["labor_hours"] or 0) for r in work_rows)
            other_direct_cost += sum(float(r["cost"] or 0) for r in work_rows)
            count += len(work_rows)
        direct_cost = other_direct_cost + parts_cost
        return {"labor_hours": labor_hours, "direct_cost": direct_cost, "other_direct_cost": other_direct_cost, "parts_cost": parts_cost, "labor_value": labor_value, "grand_total": direct_cost + labor_value, "records": count, "rate": 0}

    def save_state(self, key: str, value: str):
        self.db.execute("INSERT INTO app_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.db.commit()

    def load_state(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def app_settings(self) -> dict:
        return {key: self.load_state(key, default) for key, default in DEFAULT_SETTINGS.items()}

    def save_app_settings(self, values: dict):
        for key, default in DEFAULT_SETTINGS.items():
            self.save_state(key, values.get(key, default))

    def save_app_state(self, state: dict):
        for key, value in state.items():
            self.save_state(key, str(value or ""))

    def clear_all_data(self):
        self.db.execute("DELETE FROM notes")
        self.db.execute("DELETE FROM maintenance")
        self.db.execute("DELETE FROM work_items")
        self.db.execute("DELETE FROM vehicles")
        self.db.execute("DELETE FROM links")
        self.db.execute("DELETE FROM technicians")
        self.db.execute("DELETE FROM app_state")
        self.db.execute("UPDATE profile SET name='', rank='', labor_cost=0, updated_at=? WHERE id=1", (nowstamp(),))
        self.db.commit()

    def maintenance_all(self):
        rows = self.db.execute("""SELECT m.*, v.nickname, v.vin, v.year, v.make, v.model
                                  FROM maintenance m JOIN vehicles v ON v.id=m.vehicle_id""").fetchall()
        return sorted(rows, key=lambda r: (date_sort_key(r["service_start_date"] or r["service_date"]), r["id"]), reverse=True)

    def dashboard_data(self):
        vehicles = self.vehicles()
        mx = self.maintenance_all()
        work = self.work_items()
        totals = self.totals()
        by_vehicle = []
        by_category = defaultdict(lambda: {"count": 0, "cost": 0.0, "labor": 0.0})
        parts = Counter()
        repeats = Counter()
        due = []
        today = date_sort_key(today_date())
        for row in mx:
            vname = row["nickname"] or " ".join(x for x in [row["year"], row["make"], row["model"]] if x) or row["vin"]
            structured = self.mx_parts(row["id"])
            part_total = sum(float(p["total_cost"] or 0) for p in structured)
            labor_total = sum(float(p["labor_hours"] or 0) for p in structured)
            by_category[row["category"] or "Uncategorized"]["count"] += 1
            by_category[row["category"] or "Uncategorized"]["cost"] += part_total
            by_category[row["category"] or "Uncategorized"]["labor"] += labor_total
            repeats[(vname, (row["category"] or row["description"] or "Uncategorized")[:45])] += 1
            if structured:
                for part_row in structured:
                    name = str(part_row["part_name"] or "").strip()
                    if name:
                        parts[name] += 1
            if row["next_due"] and date_sort_key(row["next_due"]) <= today:
                due.append(row)
        for v in vehicles:
            vt = self.totals(None, None, v["id"])
            by_vehicle.append((v, vt))
        by_vehicle.sort(key=lambda item: item[1]["grand_total"], reverse=True)
        return {"vehicles": vehicles, "mx": mx, "work": work, "totals": totals, "by_vehicle": by_vehicle, "by_category": by_category, "parts": parts, "repeats": repeats, "due": due}

    def parts_history(self, vehicle_id: int):
        structured = self.structured_parts_for_vehicle(vehicle_id)
        if structured:
            return structured
        return []

    def links(self):
        return self.db.execute("SELECT * FROM links ORDER BY sort_order,id").fetchall()

    def add_link(self, data: dict):
        order = self.db.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM links").fetchone()[0]
        self.db.execute("""INSERT INTO links(title,url,sort_order,user_added,contact_name,contact_title,email,phone,address,notes)
                          VALUES(?,?,?,1,?,?,?,?,?,?)""",
                        (data.get("title", ""), data.get("url", ""), order, data.get("contact_name", ""), data.get("contact_title", ""), data.get("email", ""), data.get("phone", ""), data.get("address", ""), data.get("notes", "")))
        self.db.commit()

    def update_link(self, lid: int, data: dict):
        self.db.execute("""UPDATE links SET title=?, url=?, contact_name=?, contact_title=?, email=?, phone=?, address=?, notes=? WHERE id=?""",
                        (data.get("title", ""), data.get("url", ""), data.get("contact_name", ""), data.get("contact_title", ""), data.get("email", ""), data.get("phone", ""), data.get("address", ""), data.get("notes", ""), lid))
        self.db.commit()

    def delete_link(self, lid: int):
        self.db.execute("DELETE FROM links WHERE id=?", (lid,)); self.db.commit()


class EntryDialog(simpledialog.Dialog):
    def __init__(self, parent, title, fields):
        self.fields = fields
        self.values = None
        super().__init__(parent, title)
    def body(self, master):
        self.vars = {}
        first_entry = None
        for r, (key, label, default) in enumerate(self.fields):
            ttk.Label(master, text=label).grid(row=r, column=0, sticky="w", padx=4, pady=4)
            var = tk.StringVar(value=default)
            ent = ttk.Entry(master, textvariable=var, width=58)
            ent.grid(row=r, column=1, sticky="ew", padx=4, pady=4)
            if first_entry is None:
                first_entry = ent
            self.vars[key] = var
        return first_entry
    def validate(self):
        for key, var in self.vars.items():
            if key in DATE_INPUT_KEYS:
                try:
                    required = key in {"service_start_date", "work_date"}
                    var.set(normalize_date_input(var.get(), DATE_INPUT_LABELS.get(key, "Date"), required=required))
                except ValueError as exc:
                    messagebox.showerror(APP_NAME, str(exc), parent=self)
                    return False
        return True
    def apply(self):
        self.values = {k: v.get().strip() for k, v in self.vars.items()}


class PartDialog(simpledialog.Dialog):
    def __init__(self, parent, title="Maintenance Part", values=None, supplier_rows=None, technician_rows=None, default_technician_id=None):
        self.initial = values or {}
        self.supplier_rows = [dict(r) for r in (supplier_rows or [])]
        self.supplier_by_title = {r.get("title", ""): r for r in self.supplier_rows if r.get("title")}
        self.technician_rows = [dict(r) for r in (technician_rows or []) if int(dict(r).get("active", 1) or 0)]
        self.technician_by_label = {}
        self.default_technician_id = default_technician_id
        self.values = None
        super().__init__(parent, title)

    def body(self, master):
        self.vars = {}
        fields = [
            ("part_name", "Part name", self.initial.get("part_name", "")),
            ("part_number", "Part number", self.initial.get("part_number", "")),
        ]
        first = None
        row = 0
        for key, label, default in fields:
            ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            var = tk.StringVar(value=default)
            ent = ttk.Entry(master, textvariable=var, width=54)
            ent.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
            if first is None:
                first = ent
            self.vars[key] = var
            row += 1

        ttk.Label(master, text="Supplier used").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        self.vars["supplier"] = tk.StringVar(value=self.initial.get("supplier", ""))
        supplier_values = sorted(self.supplier_by_title)
        self.supplier_combo = ttk.Combobox(master, textvariable=self.vars["supplier"], values=supplier_values, width=52)
        self.supplier_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        self.supplier_combo.bind("<<ComboboxSelected>>", self.fill_supplier_details)
        row += 1

        detail_fields = [
            ("supplier_url", "Supplier website", self.initial.get("supplier_url", "")),
            ("supplier_contact_name", "Supplier point of contact", self.initial.get("supplier_contact_name", "")),
            ("supplier_contact_title", "Supplier contact role", self.initial.get("supplier_contact_title", "")),
            ("supplier_email", "Supplier email", self.initial.get("supplier_email", "")),
            ("supplier_phone", "Supplier phone", self.initial.get("supplier_phone", "")),
            ("supplier_address", "Supplier address/location", self.initial.get("supplier_address", "")),
            ("supplier_notes", "Supplier/source notes", self.initial.get("supplier_notes", "")),
            ("date_ordered", "Date ordered (DD MMM YYYY)", self.initial.get("date_ordered", "")),
            ("quantity", "Quantity", str(self.initial.get("quantity", "1") or "1")),
            ("unit_cost", "Unit cost", str(self.initial.get("unit_cost", "0") or "0")),
        ]
        for key, label, default in detail_fields:
            ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            var = tk.StringVar(value=default)
            ent = ttk.Entry(master, textvariable=var, width=54)
            ent.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
            self.vars[key] = var
            row += 1
        ttk.Label(master, text="Technician").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        initial_tid = str(self.initial.get("technician_id") or self.default_technician_id or "")
        tech_labels = []
        initial_label = ""
        for tech in self.technician_rows:
            label = f"{tech.get('name','')} — {tech.get('rank','')} — ${float(tech.get('labor_rate') or 0):.2f}/hr".replace(" —  — ", " — ")
            tech_labels.append(label)
            self.technician_by_label[label] = tech
            if str(tech.get("id")) == initial_tid:
                initial_label = label
        self.vars["technician"] = tk.StringVar(value=initial_label or (tech_labels[0] if tech_labels else ""))
        self.tech_combo = ttk.Combobox(master, textvariable=self.vars["technician"], values=tech_labels, state="readonly", width=52)
        self.tech_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        row += 1
        ttk.Label(master, text="Labor hours").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        self.vars["labor_hours"] = tk.StringVar(value=str(self.initial.get("labor_hours", "0") or "0"))
        ttk.Entry(master, textvariable=self.vars["labor_hours"], width=54).grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        row += 1
        ttk.Label(master, text="Part notes").grid(row=row, column=0, sticky="w", padx=4, pady=4)
        self.vars["notes"] = tk.StringVar(value=self.initial.get("notes", ""))
        ttk.Entry(master, textvariable=self.vars["notes"], width=54).grid(row=row, column=1, sticky="ew", padx=4, pady=4)
        row += 1
        ttk.Label(master, text="Select a saved supplier/source or type a new one. New supplier details are saved into Suppliers/Sources.", wraplength=520).grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 4))
        row += 1
        ttk.Label(master, text="Total is calculated from quantity × unit cost.").grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 4))
        return first

    def fill_supplier_details(self, event=None):
        row = self.supplier_by_title.get(self.vars["supplier"].get().strip())
        if not row:
            return
        mapping = {
            "supplier_url": "url",
            "supplier_contact_name": "contact_name",
            "supplier_contact_title": "contact_title",
            "supplier_email": "email",
            "supplier_phone": "phone",
            "supplier_address": "address",
            "supplier_notes": "notes",
        }
        for dest, src in mapping.items():
            self.vars[dest].set(row.get(src, "") or "")

    def validate(self):
        if not self.vars["part_name"].get().strip():
            messagebox.showerror(APP_NAME, "Part name is required.", parent=self)
            return False
        try:
            self.vars["date_ordered"].set(normalize_optional_date(self.vars["date_ordered"].get(), "Date ordered"))
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return False
        for key, label in [("quantity", "Quantity"), ("unit_cost", "Unit cost"), ("labor_hours", "Labor hours")]:
            try:
                float(self.vars[key].get() or 0)
            except ValueError:
                messagebox.showerror(APP_NAME, f"{label} must be a number.", parent=self)
                return False
        if self.technician_rows and self.vars["technician"].get() not in self.technician_by_label:
            messagebox.showerror(APP_NAME, "Select a technician.", parent=self)
            return False
        return True

    def apply(self):
        qty = float(self.vars["quantity"].get() or 0)
        unit = float(self.vars["unit_cost"].get() or 0)
        labor_hours = float(self.vars["labor_hours"].get() or 0)
        self.values = {k: v.get().strip() for k, v in self.vars.items() if k != "technician"}
        tech = self.technician_by_label.get(self.vars["technician"].get())
        if tech:
            self.values["technician_id"] = tech.get("id")
            self.values["technician_name"] = tech.get("name", "")
            self.values["technician_rank"] = tech.get("rank", "")
            self.values["technician_labor_rate"] = float(tech.get("labor_rate") or 0)
        self.values["quantity"] = qty
        self.values["unit_cost"] = unit
        self.values["total_cost"] = round(qty * unit, 2)
        self.values["labor_hours"] = labor_hours
        self.values["labor_value"] = round(labor_hours * float(self.values.get("technician_labor_rate") or 0), 2)


class MaintenanceDialog(simpledialog.Dialog):
    def __init__(self, parent, title, fields, parts=None, supplier_rows=None, technician_rows=None, default_technician_id=None):
        self.fields = fields
        self.parts = [dict(p) for p in (parts or [])]
        self.supplier_rows = supplier_rows or []
        self.technician_rows = technician_rows or []
        self.default_technician_id = default_technician_id
        self.values = None
        super().__init__(parent, title)

    def body(self, master):
        self.vars = {}
        first = None
        for r, (key, label, default) in enumerate(self.fields):
            ttk.Label(master, text=label).grid(row=r, column=0, sticky="w", padx=4, pady=3)
            var = tk.StringVar(value=default)
            ent = ttk.Entry(master, textvariable=var, width=62)
            ent.grid(row=r, column=1, columnspan=3, sticky="ew", padx=4, pady=3)
            if first is None:
                first = ent
            self.vars[key] = var
        row = len(self.fields)
        ttk.Label(master, text="Parts for this maintenance record").grid(row=row, column=0, columnspan=4, sticky="w", padx=4, pady=(10, 3))
        row += 1
        self.part_tree = ttk.Treeview(master, columns=("name", "number", "supplier", "technician", "ordered", "qty", "unit", "total", "labor"), show="headings", height=6)
        for col, label, width in [
            ("name", "Part", 160), ("number", "Part #", 90), ("supplier", "Supplier", 125), ("technician", "Technician", 135),
            ("ordered", "Ordered", 85), ("qty", "Qty", 50), ("unit", "Unit", 65), ("total", "Part Total", 75), ("labor", "Labor", 75),
        ]:
            self.part_tree.heading(col, text=label)
            self.part_tree.column(col, width=width, anchor="w")
        self.part_tree.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=4, pady=3)
        row += 1
        ttk.Button(master, text="Add Part", command=self.add_part).grid(row=row, column=0, sticky="ew", padx=4, pady=3)
        ttk.Button(master, text="Edit Part", command=self.edit_part).grid(row=row, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(master, text="Remove Part", command=self.remove_part).grid(row=row, column=2, sticky="ew", padx=4, pady=3)
        self.parts_total_var = tk.StringVar(value="")
        ttk.Label(master, textvariable=self.parts_total_var).grid(row=row, column=3, sticky="e", padx=4, pady=3)
        master.grid_columnconfigure(1, weight=1)
        self.refresh_parts()
        return first

    def selected_part_index(self):
        sel = self.part_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a part first.", parent=self)
            return None
        return int(sel[0])

    def refresh_parts(self):
        self.part_tree.delete(*self.part_tree.get_children())
        total = 0.0
        labor_total = 0.0
        for idx, p in enumerate(self.parts):
            qty = float(p.get("quantity") or 0)
            unit = float(p.get("unit_cost") or 0)
            line = round(qty * unit, 2)
            labor_hours = float(p.get("labor_hours") or 0)
            labor_rate = float(p.get("technician_labor_rate") or 0)
            labor_value = round(labor_hours * labor_rate, 2)
            p["total_cost"] = line
            p["labor_value"] = labor_value
            total += line
            labor_total += labor_value
            self.part_tree.insert("", "end", iid=str(idx), values=(p.get("part_name", ""), p.get("part_number", ""), p.get("supplier", ""), p.get("technician_name", ""), p.get("date_ordered", ""), f"{qty:g}", f"${unit:.2f}", f"${line:.2f}", f"${labor_value:.2f}"))
        self.parts_total_var.set(f"Parts: ${total:.2f}  Labor: ${labor_total:.2f}")

    def add_part(self):
        d = PartDialog(self, "Add Part", supplier_rows=self.supplier_rows, technician_rows=self.technician_rows, default_technician_id=self.default_technician_id)
        if d.values:
            self.parts.append(d.values)
            self.refresh_parts()

    def edit_part(self):
        idx = self.selected_part_index()
        if idx is None:
            return
        d = PartDialog(self, "Edit Part", self.parts[idx], supplier_rows=self.supplier_rows, technician_rows=self.technician_rows, default_technician_id=self.default_technician_id)
        if d.values:
            self.parts[idx] = d.values
            self.refresh_parts()

    def remove_part(self):
        idx = self.selected_part_index()
        if idx is None:
            return
        del self.parts[idx]
        self.refresh_parts()

    def validate(self):
        for key, var in self.vars.items():
            if key in DATE_INPUT_KEYS:
                try:
                    required = key == "service_start_date"
                    var.set(normalize_date_input(var.get(), DATE_INPUT_LABELS.get(key, "Date"), required=required))
                except ValueError as exc:
                    messagebox.showerror(APP_NAME, str(exc), parent=self)
                    return False
        return True

    def apply(self):
        self.values = {k: v.get().strip() for k, v in self.vars.items()}
        self.values["structured_parts"] = self.parts


class TechnicianSelectDialog(simpledialog.Dialog):
    def __init__(self, parent, store):
        self.store = store
        self.values = None
        super().__init__(parent, "Select Technician")

    def body(self, master):
        ttk.Label(master, text="Select the default technician for new itemized parts/labor.", wraplength=420).grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=6)
        self.var = tk.StringVar()
        self.combo = ttk.Combobox(master, textvariable=self.var, state="readonly", width=48)
        self.combo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        ttk.Button(master, text="Add Technician", command=self.add_technician).grid(row=1, column=2, sticky="ew", padx=4, pady=4)
        self.refresh()
        return self.combo

    def refresh(self):
        self.labels = {}
        values = []
        default = self.store.default_technician()
        default_id = str(default["id"]) if default else ""
        selected = ""
        for tech in self.store.technicians(include_inactive=False):
            label = f"{tech['name']} — {tech['rank']} — ${float(tech['labor_rate'] or 0):.2f}/hr".replace(" —  — ", " — ")
            self.labels[label] = tech["id"]
            values.append(label)
            if str(tech["id"]) == default_id:
                selected = label
        self.combo.configure(values=values)
        self.var.set(selected or (values[0] if values else ""))

    def add_technician(self):
        d = EntryDialog(self, "Add Technician", [("name", "Name", ""), ("rank", "Rank", ""), ("labor_rate", "Labor cost per hour", "0"), ("active", "Active? 1=yes, 0=no", "1")])
        if d.values:
            try:
                tid = self.store.add_technician(d.values)
                self.store.set_default_technician(tid)
                self.refresh()
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=self)

    def validate(self):
        if self.var.get() not in self.labels:
            messagebox.showerror(APP_NAME, "Select or add a technician.", parent=self)
            return False
        return True

    def apply(self):
        self.values = {"technician_id": self.labels[self.var.get()]}


class TechnicianManagerDialog(simpledialog.Dialog):
    def __init__(self, parent, store):
        self.store = store
        self.values = None
        super().__init__(parent, "Technicians")

    def body(self, master):
        self.listbox = tk.Listbox(master, width=70, height=10)
        self.listbox.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=4, pady=4)
        ttk.Button(master, text="Add", command=self.add).grid(row=1, column=0, sticky="ew", padx=3, pady=4)
        ttk.Button(master, text="Edit", command=self.edit).grid(row=1, column=1, sticky="ew", padx=3, pady=4)
        ttk.Button(master, text="Mark Active/Inactive", command=self.toggle_active).grid(row=1, column=2, sticky="ew", padx=3, pady=4)
        ttk.Button(master, text="Set Default", command=self.set_default).grid(row=1, column=3, sticky="ew", padx=3, pady=4)
        ttk.Button(master, text="Delete", command=self.delete).grid(row=1, column=4, sticky="ew", padx=3, pady=4)
        master.grid_columnconfigure(0, weight=1)
        self.refresh()
        return self.listbox

    def refresh(self):
        self.rows = list(self.store.technicians(include_inactive=True))
        default = self.store.default_technician()
        default_id = default["id"] if default else None
        self.listbox.delete(0, "end")
        for tech in self.rows:
            state = "active" if int(tech["active"] or 0) else "inactive"
            marker = " [default]" if tech["id"] == default_id else ""
            self.listbox.insert("end", f"{tech['name']} | {tech['rank']} | ${float(tech['labor_rate'] or 0):.2f}/hr | {state}{marker}")

    def selected(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a technician first.", parent=self)
            return None
        return self.rows[sel[0]]

    def fields(self, row=None):
        row = row or {}
        get = row.get if hasattr(row, "get") else lambda k, d="": row[k]
        return [("name", "Name", get("name", "")), ("rank", "Rank", get("rank", "")), ("labor_rate", "Labor cost per hour", str(get("labor_rate", "0") or "0")), ("active", "Active? 1=yes, 0=no", str(get("active", "1") if get("active", "1") is not None else "1"))]

    def add(self):
        d = EntryDialog(self, "Add Technician", self.fields({}))
        if d.values:
            try:
                tid = self.store.add_technician(d.values)
                self.store.set_default_technician(tid)
                self.refresh()
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=self)

    def edit(self):
        row = self.selected()
        if not row: return
        d = EntryDialog(self, "Edit Technician", self.fields(row))
        if d.values:
            try:
                self.store.update_technician(row["id"], d.values)
                self.refresh()
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=self)

    def toggle_active(self):
        row = self.selected()
        if not row: return
        data = dict(row)
        data["active"] = "0" if int(row["active"] or 0) else "1"
        try:
            self.store.update_technician(row["id"], data)
            self.refresh()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)

    def set_default(self):
        row = self.selected()
        if not row: return
        try:
            if not int(row["active"] or 0):
                raise ValueError("Default technician must be active.")
            self.store.set_default_technician(row["id"])
            self.refresh()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)

    def delete(self):
        row = self.selected()
        if not row: return
        if not messagebox.askyesno(APP_NAME, f"Delete technician {row['name']}? Used technicians cannot be deleted.", parent=self):
            return
        try:
            self.store.delete_technician(row["id"])
            self.refresh()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)

    def apply(self):
        self.values = {"updated": True}


class App:
    def safe_geometry(self, geometry: str) -> str:
        geometry = geometry or "1500x860"
        m = re.match(r"^(\d+)x(\d+)([+-]\d+)?([+-]\d+)?$", geometry)
        if not m:
            return "1500x860"
        w, h = int(m.group(1)), int(m.group(2))
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        # Keep window inside visible desktop; leave room for panels/taskbars.
        max_w = max(1100, sw - 100)
        max_h = max(640, sh - 150)
        w = min(max(w, 1100), max_w)
        h = min(max(h, 640), max_h)
        return f"{w}x{h}+20+20"

    def __init__(self, root):
        self.root = root; self.store = Store(); self.selected_vehicle_id = None
        self.root.title(APP_NAME)
        self.settings = self.store.app_settings()
        ACTIVE_SETTINGS.update(self.settings)
        self.root.geometry(self.safe_geometry("1500x860")); self.root.minsize(1100,640)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if self.settings.get("open_fullscreen", "1") == "1":
            self.root.after(100, self.open_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", lambda _e: self.on_close())
        try:
            self.font_size = int(self.store.load_state("font_size", "9") or 9)
        except Exception:
            self.font_size = 9
        self.font_size = max(8, min(18, self.font_size))
        self.vin_var = tk.StringVar(); self.status_var = tk.StringVar(value="Ready. Enter a VIN or select a saved vehicle.")
        self.build_ui(); self.refresh_all(); self.root.after(300, self.restore_last_selection); self.root.after(500, self.prompt_profile_if_needed)

    def build_ui(self):
        self.colors = THEMES.get(self.settings.get("theme", "blue"), THEMES["blue"])
        self.root.configure(bg=self.colors["bg"])
        st = ttk.Style(); st.theme_use("clam")
        st.configure("TFrame", background=self.colors["bg"]); st.configure("Card.TFrame", background=self.colors["card"])
        self.apply_font_style(st)
        main = ttk.Frame(self.root, padding=8); main.pack(fill="both", expand=True)
        ttk.Label(main, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        top = ttk.Frame(main, style="Card.TFrame", padding=6); top.pack(fill="x", pady=(6,6))
        ttk.Label(top, text="VIN", style="Card.TLabel").pack(side="left", padx=(0,8))
        ttk.Entry(top, textvariable=self.vin_var, width=28, font=("Courier New", 16, "bold")).pack(side="left")
        ttk.Button(top, text="Decode VIN", command=self.decode_thread).pack(side="left", padx=4)
        ttk.Button(top, text="Save Vehicle by Reg Number", command=self.add_manual_vehicle).pack(side="left", padx=4)
        ttk.Button(top, text="Export TXT", command=self.export_record).pack(side="right", padx=4)
        ttk.Button(top, text="Technician / Totals", command=self.show_profile_totals).pack(side="right", padx=4)
        ttk.Button(top, text="Technicians", command=self.edit_profile).pack(side="right", padx=4)
        ttk.Button(top, text="Quick Guide", command=self.show_quick_guide).pack(side="right", padx=4)
        ttk.Button(top, text="A+", width=3, command=self.increase_font).pack(side="right", padx=2)
        ttk.Button(top, text="A-", width=3, command=self.decrease_font).pack(side="right", padx=2)
        ttk.Label(main, textvariable=self.status_var).pack(anchor="w", pady=(0,2))
        self.panes = ttk.PanedWindow(main, orient="horizontal"); self.panes.pack(fill="both", expand=True, pady=(4,6))
        left = ttk.Frame(self.panes, style="Card.TFrame", padding=8); mid = ttk.Frame(self.panes, style="Card.TFrame", padding=8); right = ttk.Frame(self.panes, style="Card.TFrame", padding=8)
        self.panes.add(left, weight=2); self.panes.add(mid, weight=3); self.panes.add(right, weight=4)
        self.root.after(600, self.restore_panel_sizes)
        ttk.Label(left, text="Saved Vehicles", style="Card.TLabel", font=("Arial", 12, "bold")).pack(anchor="w")
        ttk.Label(left, text="Local saved vehicles", style="Card.TLabel", font=("Arial", 9)).pack(anchor="w")
        vsearch = ttk.Frame(left, style="Card.TFrame"); vsearch.pack(fill="x", pady=(4,2))
        self.vehicle_search_var = tk.StringVar()
        vent = ttk.Entry(vsearch, textvariable=self.vehicle_search_var)
        vent.pack(side="left", fill="x", expand=True)
        vent.bind("<KeyRelease>", lambda _e: self.refresh_vehicle_list())
        ttk.Button(vsearch, text="X", width=3, command=self.clear_vehicle_search).pack(side="left", padx=2)
        self.vehicle_list = tk.Listbox(left, bg=self.colors["panel"], fg=self.colors["fg"], selectbackground=self.colors["select"], relief="flat", font=("Arial", 8))
        self.vehicle_list.pack(fill="both", expand=True, pady=4); self.vehicle_list.bind("<<ListboxSelect>>", lambda e: self.select_vehicle()); self.vehicle_list.bind("<Double-Button-1>", lambda e: self.open_selected_vehicle()); self.vehicle_list.bind("<Return>", lambda e: self.open_selected_vehicle())
        ttk.Button(left, text="Reg Number", command=self.nickname_vehicle).pack(fill="x", pady=1)
        ttk.Button(left, text="Edit Vehicle Info", command=self.edit_vehicle_info).pack(fill="x", pady=1)
        ttk.Button(left, text="Delete Vehicle", command=self.delete_vehicle).pack(fill="x", pady=1)
        ttk.Button(left, text="Clear ALL Saved Info", command=self.clear_all_saved_info).pack(fill="x", pady=(6,1))
        info_frame = ttk.Frame(mid, style="Card.TFrame"); info_frame.pack(fill="both", expand=True)
        self.info = tk.Text(info_frame, bg=self.colors["panel"], fg=self.colors["fg"], font=("Courier New", 9), wrap="word", relief="flat")
        info_scroll = ttk.Scrollbar(info_frame, orient="vertical", command=self.info.yview)
        self.info.configure(yscrollcommand=info_scroll.set)
        self.info.pack(side="left", fill="both", expand=True); info_scroll.pack(side="right", fill="y")
        nb = ttk.Notebook(right); nb.pack(fill="both", expand=True)
        dash_tab = ttk.Frame(nb, padding=6); notes_tab = ttk.Frame(nb, padding=6); mx_tab = ttk.Frame(nb, padding=6); work_tab = ttk.Frame(nb, padding=6); search_tab = ttk.Frame(nb, padding=6); links_tab = ttk.Frame(nb, padding=6); backup_tab = ttk.Frame(nb, padding=6); settings_tab = ttk.Frame(nb, padding=6)
        nb.add(dash_tab, text="Dashboard"); nb.add(notes_tab, text="Notes"); nb.add(mx_tab, text="Vehicle MX"); nb.add(work_tab, text="Other Work"); nb.add(search_tab, text="Search"); nb.add(links_tab, text="Suppliers/Sources"); nb.add(backup_tab, text="Backup"); nb.add(settings_tab, text="Settings")
        dash_text_frame = ttk.Frame(dash_tab); dash_text_frame.pack(fill="both", expand=True)
        self.dashboard = tk.Text(dash_text_frame, bg=self.colors["panel"], fg=self.colors["fg"], font=("Courier New", 9), wrap="word", relief="flat", height=10)
        dash_scroll = ttk.Scrollbar(dash_text_frame, orient="vertical", command=self.dashboard.yview)
        self.dashboard.configure(yscrollcommand=dash_scroll.set)
        self.dashboard.pack(side="left", fill="both", expand=True); dash_scroll.pack(side="right", fill="y")
        ttk.Button(dash_tab, text="Refresh Dashboard / Trends", command=self.refresh_dashboard).pack(fill="x", pady=1)
        ttk.Button(dash_tab, text="Show Overdue / Due Now", command=self.show_due_alerts).pack(fill="x", pady=1)
        self.notes = tk.Listbox(notes_tab, bg=self.colors["panel"], fg=self.colors["fg"], selectbackground=self.colors["select"], relief="flat"); self.notes.pack(fill="both", expand=True)
        self.notes.bind("<Double-Button-1>", lambda e: self.edit_note()); self.notes.bind("<Return>", lambda e: self.edit_note())
        ttk.Button(notes_tab, text="Add Dated Note", command=self.add_note).pack(fill="x", pady=1)
        ttk.Button(notes_tab, text="Edit Selected Note", command=self.edit_note).pack(fill="x", pady=1)
        ttk.Button(notes_tab, text="Delete Selected Note", command=self.delete_note).pack(fill="x", pady=1)
        self.mx = tk.Listbox(mx_tab, bg=self.colors["panel"], fg=self.colors["fg"], selectbackground=self.colors["select"], relief="flat")
        self.mx.pack(fill="both", expand=True)
        self.mx.bind("<Double-Button-1>", lambda e: self.edit_mx()); self.mx.bind("<Return>", lambda e: self.edit_mx())
        ttk.Button(mx_tab, text="Add Maintenance Record", command=self.add_mx).pack(fill="x", pady=1)
        ttk.Button(mx_tab, text="Edit Selected Record", command=self.edit_mx).pack(fill="x", pady=1)
        ttk.Button(mx_tab, text="Delete Selected Record", command=self.delete_mx).pack(fill="x", pady=1)
        ttk.Button(mx_tab, text="Show Vehicle Parts History", command=self.show_parts_history).pack(fill="x", pady=(8,2))
        self.work = tk.Listbox(work_tab, bg=self.colors["panel"], fg=self.colors["fg"], selectbackground=self.colors["select"], relief="flat")
        self.work.pack(fill="both", expand=True)
        self.work.bind("<Double-Button-1>", lambda e: self.edit_work()); self.work.bind("<Return>", lambda e: self.edit_work())
        ttk.Button(work_tab, text="Add Unlinked Work", command=self.add_work).pack(fill="x", pady=1)
        ttk.Button(work_tab, text="Edit Selected Work", command=self.edit_work).pack(fill="x", pady=1)
        ttk.Button(work_tab, text="Delete Selected Work", command=self.delete_work).pack(fill="x", pady=1)
        srow = ttk.Frame(search_tab); srow.pack(fill="x")
        self.search_var = tk.StringVar()
        ttk.Entry(srow, textvariable=self.search_var).pack(side="left", fill="x", expand=True)
        ttk.Button(srow, text="Search", command=self.run_search).pack(side="left", padx=4)
        ttk.Button(srow, text="Open Selected", command=self.open_search_result).pack(side="left", padx=4)
        self.search = ttk.Treeview(search_tab, columns=("kind","date","vehicle","text","cost"), show="headings", height=10)
        for c,t,w in [("kind","Type",90),("date","Date",85),("vehicle","Vehicle/Title",130),("text","Text",260),("cost","Cost",70)]: self.search.heading(c,text=t); self.search.column(c,width=w)
        self.search.pack(fill="both", expand=True, pady=4)

        self.links = tk.Listbox(links_tab, bg=self.colors["panel"], fg=self.colors["fg"], selectbackground=self.colors["select"], relief="flat"); self.links.pack(fill="both", expand=True)
        self.links.bind("<Double-Button-1>", lambda e: self.view_supplier_details())
        ttk.Button(links_tab, text="Add Supplier/Source", command=self.add_link).pack(fill="x", pady=1)
        ttk.Button(links_tab, text="Edit Supplier/Source", command=self.edit_link).pack(fill="x", pady=1)
        ttk.Button(links_tab, text="Delete Supplier/Source", command=self.delete_link).pack(fill="x", pady=1)
        ttk.Button(links_tab, text="View Supplier/Source Details", command=self.view_supplier_details).pack(fill="x", pady=1)
        ttk.Button(links_tab, text="Open Website", command=self.open_link).pack(fill="x", pady=1)
        ttk.Label(backup_tab, text="Backup / Restore", font=("Arial", 12, "bold")).pack(anchor="w")
        ttk.Button(backup_tab, text="Backup Database", command=self.backup_database).pack(fill="x", pady=4)
        ttk.Button(backup_tab, text="Restore Database", command=self.restore_database).pack(fill="x", pady=4)
        ttk.Label(backup_tab, text="Backups copy the local SQLite database. Restore replaces current app data after confirmation.", wraplength=360).pack(anchor="w", pady=6)
        ttk.Label(settings_tab, text="Settings", font=("Arial", 12, "bold")).pack(anchor="w")
        self.font_label_var = tk.StringVar(value=f"Font size: {self.font_size}")
        ttk.Label(settings_tab, textvariable=self.font_label_var).pack(anchor="w", pady=4)
        ttk.Button(settings_tab, text="Increase Font Size", command=self.increase_font).pack(fill="x", pady=2)
        ttk.Button(settings_tab, text="Decrease Font Size", command=self.decrease_font).pack(fill="x", pady=2)
        ttk.Button(settings_tab, text="Reset Font Size", command=self.reset_font).pack(fill="x", pady=2)
        ttk.Button(settings_tab, text="Change Color Theme", command=self.change_theme).pack(fill="x", pady=8)
        ttk.Button(settings_tab, text="Edit NHTSA URLs", command=self.edit_nhtsa_urls).pack(fill="x", pady=2)
        ttk.Button(settings_tab, text="Toggle Open Fullscreen", command=self.toggle_open_fullscreen_setting).pack(fill="x", pady=2)
        ttk.Button(settings_tab, text="Toggle Auto Refresh NHTSA", command=self.toggle_auto_refresh_setting).pack(fill="x", pady=2)
        ttk.Button(settings_tab, text="Reset Settings to Defaults", command=self.reset_app_settings).pack(fill="x", pady=8)
        ttk.Button(settings_tab, text="Save Settings Now", command=self.autosave_app_state).pack(fill="x", pady=2)
        ttk.Label(settings_tab, text="Settings are saved locally and restored next time. Double-click or press Enter on saved vehicles, search results, notes, Vehicle MX, Other Work, and Suppliers/Sources to open or edit the selected item.", wraplength=360).pack(anchor="w", pady=6)
        self.apply_font_style(st)

    def apply_font_style(self, st=None):
        st = st or ttk.Style()
        fs = self.font_size
        c = getattr(self, "colors", THEMES.get(getattr(self, "settings", {}).get("theme", "blue"), THEMES["blue"]))
        st.configure("TLabel", background=c["bg"], foreground=c["fg"], font=("Arial", fs))
        st.configure("Card.TLabel", background=c["card"], foreground=c["fg"], font=("Arial", fs))
        st.configure("Title.TLabel", background=c["bg"], foreground=c["accent"], font=("Arial", max(fs+11, 18), "bold"))
        st.configure("TButton", font=("Arial", fs, "bold"), padding=4)
        st.configure("Treeview", font=("Arial", fs), rowheight=max(22, fs+14))
        st.configure("Treeview.Heading", font=("Arial", fs, "bold"))
        if hasattr(self, "vehicle_list"):
            for widget in [self.vehicle_list, self.notes, self.mx, self.work, self.links]:
                widget.configure(font=("Arial", fs))
            self.info.configure(font=("Courier New", fs))
            self.dashboard.configure(font=("Courier New", fs))
            if hasattr(self, "font_label_var"):
                self.font_label_var.set(f"Font size: {self.font_size}")

    def save_font_size(self):
        self.store.save_state("font_size", str(self.font_size))

    def increase_font(self):
        self.font_size = min(18, self.font_size + 1)
        self.save_font_size(); self.apply_font_style(); self.autosave_app_state()

    def decrease_font(self):
        self.font_size = max(8, self.font_size - 1)
        self.save_font_size(); self.apply_font_style(); self.autosave_app_state()

    def reset_font(self):
        self.font_size = 9
        self.save_font_size(); self.apply_font_style(); self.autosave_app_state()

    def open_fullscreen(self):
        try:
            self.root.attributes("-fullscreen", True)
        except Exception:
            try:
                self.root.state("zoomed")
            except Exception:
                self.root.geometry(self.safe_geometry("1500x860"))
        self.status_var.set("Ready. App opened fullscreen. Press F11 to toggle fullscreen. Press Esc to close and autosave.")

    def toggle_fullscreen(self, event=None):
        try:
            current = bool(self.root.attributes("-fullscreen"))
            self.root.attributes("-fullscreen", not current)
            self.status_var.set("Fullscreen on." if not current else "Fullscreen off.")
        except Exception:
            pass

    def save_settings(self):
        self.store.save_app_settings(self.settings)
        ACTIVE_SETTINGS.update(self.settings)

    def change_theme(self):
        current = self.settings.get("theme", "blue")
        choice = simpledialog.askstring(APP_NAME, f"Color theme ({', '.join(THEMES.keys())}):", initialvalue=current)
        if choice is None:
            return
        choice = choice.strip().lower()
        if choice not in THEMES:
            messagebox.showerror(APP_NAME, f"Choose one of: {', '.join(THEMES.keys())}")
            return
        self.settings["theme"] = choice
        self.save_settings(); self.autosave_app_state()
        messagebox.showinfo(APP_NAME, "Theme saved. Restart the app to fully apply all colors.")

    def edit_nhtsa_urls(self):
        fields = [
            ("nhtsa_vpic_base", "VIN decode base URL", self.settings.get("nhtsa_vpic_base", NHTSA_BASE)),
            ("nhtsa_recall_base", "Recalls base URL", self.settings.get("nhtsa_recall_base", NHTSA_RECALL_BASE)),
            ("nhtsa_complaint_base", "Complaints base URL", self.settings.get("nhtsa_complaint_base", NHTSA_COMPLAINT_BASE)),
            ("nhtsa_products_base", "Products/TSB base URL", self.settings.get("nhtsa_products_base", NHTSA_PRODUCTS_BASE)),
        ]
        d=EntryDialog(self.root, "Edit NHTSA URLs", fields)
        if d.values is not None:
            for key in [f[0] for f in fields]:
                val = d.values.get(key, "").strip()
                if not val.startswith(("http://", "https://")):
                    messagebox.showerror(APP_NAME, f"{key} must start with http:// or https://")
                    return
                self.settings[key] = val.rstrip("/")
            self.save_settings(); self.autosave_app_state()
            self.status_var.set("Saved NHTSA URL settings.")

    def toggle_open_fullscreen_setting(self):
        self.settings["open_fullscreen"] = "0" if self.settings.get("open_fullscreen", "1") == "1" else "1"
        self.save_settings(); self.autosave_app_state()
        self.status_var.set(f"Open fullscreen setting: {'on' if self.settings['open_fullscreen']=='1' else 'off'}")

    def toggle_auto_refresh_setting(self):
        self.settings["auto_refresh_nhtsa"] = "0" if self.settings.get("auto_refresh_nhtsa", "1") == "1" else "1"
        self.save_settings(); self.autosave_app_state()
        self.status_var.set(f"Auto refresh NHTSA setting: {'on' if self.settings['auto_refresh_nhtsa']=='1' else 'off'}")

    def reset_app_settings(self):
        if not messagebox.askyesno(APP_NAME, "Reset app settings to defaults? This does not delete vehicles or records."):
            return
        self.settings = DEFAULT_SETTINGS.copy()
        self.font_size = 9
        self.save_font_size(); self.save_settings(); self.autosave_app_state()
        messagebox.showinfo(APP_NAME, "Settings reset. Restart the app to fully apply defaults.")

    def get_pane_sash(self, index):
        try:
            return str(self.panes.sashpos(index))
        except Exception:
            return self.store.load_state(f"pane_sash_{index}", "")

    def restore_panel_sizes(self):
        if not hasattr(self, "panes"):
            return
        try:
            self.root.update_idletasks()
            total = max(1, self.panes.winfo_width())
            for idx, default_ratio in [(0, 0.25), (1, 0.58)]:
                raw = self.store.load_state(f"pane_sash_{idx}", "")
                if raw and raw.isdigit():
                    pos = int(raw)
                    # Keep sashes on screen even if monitor size changed.
                    pos = max(140 if idx == 0 else 300, min(pos, total - 180))
                else:
                    pos = int(total * default_ratio)
                self.panes.sashpos(idx, pos)
        except Exception:
            pass

    def collect_app_state(self):
        return {
            "selected_vehicle_id": self.selected_vehicle_id or "",
            "vehicle_search": self.vehicle_search_var.get() if hasattr(self, "vehicle_search_var") else "",
            "record_search": self.search_var.get() if hasattr(self, "search_var") else "",
            "font_size": self.font_size,
            "pane_sash_0": self.get_pane_sash(0),
            "pane_sash_1": self.get_pane_sash(1),
            **self.settings,
            "last_saved_at": nowstamp(),
        }

    def autosave_app_state(self):
        try:
            self.store.save_app_state(self.collect_app_state())
            self.status_var.set(f"Autosaved app state at {nowstamp()}.")
        except Exception as e:
            self.status_var.set(f"Autosave warning: {e}")

    def on_close(self):
        self.autosave_app_state()
        try:
            self.store.db.commit()
        except Exception:
            pass
        self.root.destroy()

    def restore_last_selection(self):
        search = self.store.load_state("vehicle_search", "")
        if search and hasattr(self, "vehicle_search_var"):
            self.vehicle_search_var.set(search); self.refresh_vehicle_list()
        last = self.store.load_state("selected_vehicle_id", "")
        if last:
            try:
                vid = int(last)
                if self.store.get_vehicle(vid):
                    self.load_vehicle(vid)
                    for idx, row in enumerate(self.vehicle_rows):
                        if row["id"] == vid:
                            self.vehicle_list.selection_clear(0, "end")
                            self.vehicle_list.selection_set(idx)
                            self.vehicle_list.see(idx)
                            break
            except Exception:
                pass

    def refresh_all(self):
        self.refresh_vehicle_list()
        self.refresh_links(); self.refresh_work()
        if hasattr(self, "dashboard"):
            self.refresh_dashboard()
        if self.selected_vehicle_id: self.load_vehicle(self.selected_vehicle_id)

    def set_dashboard(self, text):
        self.dashboard.configure(state="normal"); self.dashboard.delete("1.0", "end"); self.dashboard.insert("1.0", text); self.dashboard.configure(state="disabled")

    def refresh_dashboard(self):
        data = self.store.dashboard_data()
        t = data["totals"]
        lines = [
            "MECHANIC DASHBOARD / MX TRENDS",
            "="*72,
            f"Vehicles: {len(data['vehicles'])}    MX records: {len(data['mx'])}    Other Work: {len(data['work'])}",
            f"Labor hours: {t['labor_hours']:.2f}    Labor value: ${t['labor_value']:.2f}",
            f"Parts total: ${t['parts_cost']:.2f}    Other Work costs: ${t['other_direct_cost']:.2f}    Grand total: ${t['grand_total']:.2f}",
            "",
            "Due / Overdue:",
        ]
        if data["due"]:
            for r in data["due"][:10]:
                vname = r["nickname"] or " ".join(x for x in [r["year"], r["make"], r["model"]] if x) or r["vin"]
                lines.append(f"  {r['next_due']} | {vname} | {r['description'] or r['category'] or '(blank record)'}")
        else:
            lines.append("  None recorded as due today/overdue.")
        lines += ["", "Highest Cost Vehicles:"]
        for v, vt in data["by_vehicle"][:8]:
            name = v["nickname"] or " ".join(x for x in [v["year"], v["make"], v["model"]] if x) or v["vin"]
            lines.append(f"  ${vt['grand_total']:.2f} | {vt['labor_hours']:.1f} hrs | {name}")
        lines += ["", "Cost by Category:"]
        cats = sorted(data["by_category"].items(), key=lambda kv: kv[1]["cost"], reverse=True)
        for cat, vals in cats[:10]:
            lines.append(f"  ${vals['cost']:.2f} | {vals['labor']:.1f} hrs | {vals['count']} records | {cat}")
        lines += ["", "Most Used Parts:"]
        for part, count in data["parts"].most_common(10):
            lines.append(f"  {count}x | {part}")
        lines += ["", "Recurring Issues / Categories:"]
        recurring = [(k,c) for k,c in data["repeats"].items() if c > 1]
        if recurring:
            for (veh, issue), count in sorted(recurring, key=lambda x: x[1], reverse=True)[:10]:
                lines.append(f"  {count}x | {veh} | {issue}")
        else:
            lines.append("  Not enough repeated records yet.")
        self.set_dashboard("\n".join(lines)+"\n")

    def show_due_alerts(self):
        data = self.store.dashboard_data()
        lines = ["DUE / OVERDUE SERVICE", "="*72]
        if data["due"]:
            for r in data["due"]:
                vname = r["nickname"] or " ".join(x for x in [r["year"], r["make"], r["model"]] if x) or r["vin"]
                lines.append(f"{r['next_due']} | {vname} | {r['description'] or r['category'] or '(blank record)'}")
        else:
            lines.append("No services are recorded as due today or overdue.")
        self.set_info("\n".join(lines)+"\n")
        self.status_var.set("Showing due/overdue service records.")

    def backup_database(self):
        target = filedialog.asksaveasfilename(initialdir=str(EXPORT_DIR), initialfile=f"veh-mx-tracker-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.sqlite3", defaultextension=".sqlite3", filetypes=[("SQLite database", "*.sqlite3"), ("All files", "*")])
        if not target:
            return
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True); Path(target).parent.mkdir(parents=True, exist_ok=True)
            self.store.db.commit()
            shutil.copy2(DB_PATH, target)
            messagebox.showinfo(APP_NAME, f"Backup saved:\n{target}")
            self.status_var.set("Database backup saved.")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def restore_database(self):
        source = filedialog.askopenfilename(title="Choose Veh Mx Tracker database backup", filetypes=[("SQLite database", "*.sqlite3"), ("All files", "*")])
        if not source:
            return
        if not messagebox.askyesno(APP_NAME, "Restore this backup? Current app data will be replaced after a safety backup is made."):
            return
        try:
            self.store.db.commit(); self.store.db.close()
            safety = DB_PATH.with_suffix(f".before-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3")
            if DB_PATH.exists(): shutil.copy2(DB_PATH, safety)
            shutil.copy2(source, DB_PATH)
            self.store = Store(); self.selected_vehicle_id = None; self.refresh_all()
            messagebox.showinfo(APP_NAME, f"Backup restored. Safety copy created:\n{safety}")
            self.status_var.set("Database restored from backup.")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))
            self.store = Store(); self.refresh_all()

    def show_quick_guide(self):
        lines = [
            "MECHANIC QUICK GUIDE",
            "="*70,
            "1. Add vehicles by VIN or Reg Number.",
            "2. Select a saved vehicle to see saved local NHTSA info. If online, it refreshes and saves new NHTSA info automatically.",
            "3. Use Notes for quick observations.",
            "4. Use Vehicle MX for service, parts, costs, mileage, hours, labor, and next due.",
            "5. Use Show Vehicle Parts History to see every part recorded for the selected vehicle.",
            "6. Use Dashboard for due service, highest-cost vehicles, parts usage, categories, and recurring trends.",
            "7. Use Search to data-mine notes, MX records, Other Work, costs, parts, and trends.",
            "8. Use Suppliers/Sources for standalone vendors and points of contact.",
            "9. Use Technician / Totals for labor hours, labor value, direct costs, and date ranges.",
            "10. Use Export TXT for a clean report.",
            "11. Use Backup to copy or restore the local database.",
            "12. The app opens fullscreen. Press F11 to toggle fullscreen. Press Esc to close and autosave.",
            "13. Closing the app autosaves search text, selected vehicle, font size, and settings. Records are saved as you add/edit them.",
        ]
        self.set_info("\n".join(lines)+"\n")
        self.status_var.set("Showing mechanic quick guide.")

    def clear_vehicle_search(self):
        self.vehicle_search_var.set("")
        self.refresh_vehicle_list()

    def refresh_vehicle_list(self):
        self.vehicle_rows = self.store.search_vehicles(self.vehicle_search_var.get() if hasattr(self, "vehicle_search_var") else "")
        self.vehicle_list.delete(0,"end")
        for v in self.vehicle_rows:
            name = v["nickname"] or " ".join(x for x in [v["year"], v["make"], v["model"]] if x) or "Manual Vehicle"
            vin_tail = "NO VIN" if str(v["vin"]).startswith("NO-VIN-") else v["vin"][-8:]
            # Keep the row readable in the left pane; full details show in the report when selected.
            self.vehicle_list.insert("end", f"{name[:26]} | {vin_tail}")

    def refresh_links(self):
        self.link_rows = self.store.links(); self.links.delete(0,"end")
        for l in self.link_rows:
            bits = [l["title"]]
            if l["contact_name"]: bits.append(l["contact_name"])
            if l["phone"]: bits.append(l["phone"])
            if l["email"]: bits.append(l["email"])
            self.links.insert("end", " | ".join(bits))

    def open_selected_vehicle(self):
        sel = self.vehicle_list.curselection()
        if sel:
            self.load_vehicle(self.vehicle_rows[sel[0]]["id"])
            self.status_var.set("Opened selected vehicle.")

    def select_vehicle(self):
        sel = self.vehicle_list.curselection()
        if sel: self.load_vehicle(self.vehicle_rows[sel[0]]["id"])

    def load_vehicle(self, vid):
        self.selected_vehicle_id = vid; v = self.store.get_vehicle(vid)
        if not v: return
        display_vin = "" if str(v["vin"]).startswith("NO-VIN-") else v["vin"]
        self.vin_var.set(display_vin); raw = json.loads(v["raw_json"] or "{}")
        raw.update({"ModelYear": v["year"], "Make": v["make"], "Model": v["model"], "Trim": v["trim"], "EngineModel": v["engine"], "BodyClass": v["body"]})
        cached = self.store.cached_vehicle_public_info(vid) if display_vin else None
        if cached:
            data = cached.get("decoded") or raw
            report = self.make_report(display_vin, data, cached.get("recalls", []), cached.get("complaints", []), cached.get("tsbs", []), cached.get("cached_at"))
            self.set_info(report)
            self.status_var.set(f"Showing saved local NHTSA info from {cached.get('cached_at','cache')}. Updating online if internet is available...")
        else:
            report = self.make_report(display_vin or "NO VIN", raw, None, None, None)
            self.set_info(report)
        self.refresh_notes(); self.refresh_mx()
        if display_vin and self.settings.get("auto_refresh_nhtsa", "1") == "1":
            self.status_var.set((self.status_var.get() if hasattr(self.status_var, 'get') else '') or "Updating NHTSA info online for selected saved vehicle...")
            threading.Thread(target=self.selected_vehicle_public_info_worker, args=(vid, display_vin, raw), daemon=True).start()

    def set_info(self, text):
        self.info.configure(state="normal"); self.info.delete("1.0","end"); self.info.insert("1.0", text); self.info.configure(state="disabled")

    def safe_nhtsa_call(self, func, default):
        try:
            return func()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return default
            raise
        except Exception:
            return default

    def selected_vehicle_public_info_worker(self, vid, vin, saved_raw):
        try:
            data = decode_vin(vin)
            # Keep manual edits visible if NHTSA leaves a field blank.
            for key, value in saved_raw.items():
                data.setdefault(key, value)
            year=data.get("ModelYear",""); make=data.get("Make",""); model=data.get("Model","")
            recalls = self.safe_nhtsa_call(lambda: nhtsa_recalls(year,make,model), []) if year and make and model else []
            complaints = self.safe_nhtsa_call(lambda: nhtsa_complaints(year,make,model), []) if year and make and model else []
            tsbs = self.safe_nhtsa_call(lambda: nhtsa_tsbs(year,make,model), []) if year and make and model else []
            report = self.make_report(vin, data, recalls, complaints, tsbs)
            self.root.after(0, lambda: self.selected_vehicle_public_info_done(vid, report, len(tsbs), len(recalls), len(complaints), data, recalls, complaints, tsbs))
        except Exception as e:
            msg=str(e)
            self.root.after(0, lambda: self.status_var.set(f"Online NHTSA update unavailable for this vehicle/query; showing saved local info if present. {msg}"))

    def selected_vehicle_public_info_done(self, vid, report, tc, rc, cc, data=None, recalls=None, complaints=None, tsbs=None):
        if data is not None:
            try:
                self.store.save_vehicle_public_info(vid, data, recalls or [], complaints or [], tsbs or [])
            except Exception:
                pass
        if self.selected_vehicle_id == vid:
            self.set_info(report)
            self.status_var.set(f"Selected vehicle updated and saved locally. TSB matches: {tc}. Recalls: {rc}. Complaints: {cc}.")

    def decode_thread(self):
        vin = self.vin_var.get().strip().upper(); self.vin_var.set(vin)
        ok,msg = validate_vin(vin)
        if not ok: messagebox.showerror(APP_NAME,msg); return
        self.status_var.set("Decoding and checking public NHTSA records...")
        threading.Thread(target=self.decode_worker, args=(vin,), daemon=True).start()

    def decode_worker(self, vin):
        try:
            data = decode_vin(vin); year=data.get("ModelYear",""); make=data.get("Make",""); model=data.get("Model","")
            recalls = self.safe_nhtsa_call(lambda: nhtsa_recalls(year,make,model), []) if year and make and model else []
            complaints = self.safe_nhtsa_call(lambda: nhtsa_complaints(year,make,model), []) if year and make and model else []
            tsbs = self.safe_nhtsa_call(lambda: nhtsa_tsbs(year,make,model), []) if year and make and model else []
            report = self.make_report(vin, data, recalls, complaints, tsbs)
            # All Tkinter and SQLite work must run on the main UI thread.
            self.root.after(0, lambda: self.after_decode(vin, data, report, len(recalls), len(complaints), len(tsbs), recalls, complaints, tsbs))
        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda: messagebox.showerror(APP_NAME, msg))
            self.root.after(0, lambda: self.status_var.set(f"Error: {msg}"))

    def after_decode(self, vin, data, report, rc, cc, tc=0, recalls=None, complaints=None, tsbs=None):
        try:
            vid = self.store.save_vehicle(vin, data)
            self.store.save_vehicle_public_info(vid, data, recalls or [], complaints or [], tsbs or [])
            self.selected_vehicle_id=vid; self.refresh_all(); self.load_vehicle(vid); self.set_info(report)
            self.status_var.set(f"Saved/updated vehicle and saved public info locally. TSB matches: {tc}. Recalls: {rc}. Complaints: {cc}.")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))
            self.status_var.set(f"Error: {e}")

    def make_report(self, vin, data, recalls, complaints, tsbs=None, cached_at=None):
        lines=[f"{APP_NAME} Record", "="*70, f"VIN: {vin}"]
        if vin == "NO VIN":
            lines.append("Validation: Manual vehicle saved without VIN")
        else:
            lines.append(f"Validation: {validate_vin(vin)[1]}")
        if cached_at:
            lines.append(f"Saved local NHTSA info updated: {cached_at}")
        lines.append("")
        labels=[("Model Year","ModelYear"),("Make","Make"),("Model","Model"),("Trim","Trim"),("Series","Series"),("Body","BodyClass"),("Engine","EngineModel"),("Displacement L","DisplacementL"),("Cylinders","EngineCylinders"),("Fuel","FuelTypePrimary"),("Drive","DriveType"),("Transmission","TransmissionStyle"),("Plant","PlantCity"),("Plant State","PlantState"),("Plant Country","PlantCountry"),("Manufacturer","Manufacturer")]
        lines += ["Decoded Vehicle", "-"*70]
        shown_keys = {key for _, key in labels}
        for lab,key in labels:
            if data.get(key): lines.append(f"{lab}: {data[key]}")
        extra_items = [(k, v) for k, v in sorted(data.items()) if k not in shown_keys and str(v).strip()]
        if extra_items:
            lines += ["", "Additional Saved NHTSA Vehicle Info", "-"*70]
            for k, v in extra_items[:120]:
                lines.append(f"{k}: {v}")
        if tsbs is not None:
            lines += ["", f"TSB model matches found: {len(tsbs)}", "-"*70]
            if tsbs:
                for i,t in enumerate(tsbs[:20],1):
                    lines.append(f"{i}. {t.get('modelYear') or t.get('ModelYear') or data.get('ModelYear','')} {t.get('make') or t.get('Make') or data.get('Make','')} {t.get('model') or t.get('Model') or data.get('Model','')}")
                lines.append("NHTSA confirms TSB product coverage for this year/make/model. Detailed bulletin summaries may not be available from the public products endpoint.")
            else: lines.append("No TSB model match returned for decoded year/make/model.")
        if recalls is not None:
            lines += ["", f"Recalls found: {len(recalls)}", "-"*70]
            if recalls:
                for i,r in enumerate(recalls[:20],1):
                    lines.append(f"{i}. {(r.get('Component') or r.get('component') or 'Recall')} {(r.get('NHTSACampaignNumber') or '')}")
                    if r.get('Summary'): lines.append(f"   {r.get('Summary')[:650]}")
            else: lines.append("No recalls returned for decoded year/make/model.")
        if complaints is not None:
            lines += ["", f"Complaints found: {len(complaints)}", "-"*70]
            if complaints:
                for i,c in enumerate(complaints[:12],1): lines.append(f"{i}. {(c.get('components') or c.get('Component') or 'Complaint')}: {(c.get('summary') or c.get('Summary') or '')[:500]}")
            else: lines.append("No complaints returned for decoded year/make/model.")
        lines += ["", "Mechanic tracking", "-"*70, "Use Notes for dated observations. Use Maintenance for service date, mileage, equipment hours, itemized parts, labor hours, and next-due info."]
        return "\n".join(lines)+"\n"

    def add_manual_vehicle(self):
        fields=[("nickname","Reg Number",""),("year","Year",""),("make","Make",""),("model","Model",""),("trim","Trim",""),("engine","Engine",""),("body","Body/Class","")]
        d=EntryDialog(self.root,"Save Vehicle by Reg Number", fields)
        if d.values is not None:
            vid=self.store.save_manual_vehicle(d.values)
            self.selected_vehicle_id=vid
            self.refresh_all(); self.load_vehicle(vid)
            self.status_var.set("Saved vehicle without VIN.")

    def prompt_profile_if_needed(self):
        if not self.store.default_technician():
            messagebox.showinfo(APP_NAME, "Select or add a technician for new itemized parts/labor.")
            d = TechnicianSelectDialog(self.root, self.store)
            if d.values:
                self.store.set_default_technician(d.values["technician_id"])
        elif not self.store.load_state("default_technician_id", ""):
            d = TechnicianSelectDialog(self.root, self.store)
            if d.values:
                self.store.set_default_technician(d.values["technician_id"])

    def edit_profile(self):
        d = TechnicianManagerDialog(self.root, self.store)
        self.status_var.set("Technician profiles updated." if d.values else "Technician profile editor closed.")

    def show_profile_totals(self):
        if not self.store.default_technician():
            self.prompt_profile_if_needed()
        d=EntryDialog(self.root,"Totals Date Range (optional)", [("start","Start date DD MMM YYYY", ""), ("end","End date DD MMM YYYY", "")])
        start=end=""
        if d.values:
            start=d.values.get("start",""); end=d.values.get("end","")
        prof = self.store.totals(start,end,None)
        default_tech = self.store.default_technician()
        lines=[f"Technician / Totals", "="*60, f"Default technician: {(default_tech['name'] if default_tech else 'None')}", f"Date range: {start or 'all'} to {end or 'all'}", "", "Totals including vehicle MX itemized part labor and other work", "-"*60, f"Records: {prof['records']}", f"Labor hours: {prof['labor_hours']:.2f}", f"Labor cost value: ${prof['labor_value']:.2f}", f"Parts total: ${prof['parts_cost']:.2f}", f"Other Work costs: ${prof['other_direct_cost']:.2f}", f"Combined direct costs: ${prof['direct_cost']:.2f}", f"Grand total: ${prof['grand_total']:.2f}", "", "Technicians:"]
        for tech in self.store.technicians(include_inactive=True):
            lines.append(f"  {tech['name']} | {tech['rank']} | ${float(tech['labor_rate'] or 0):.2f}/hr | {'active' if int(tech['active'] or 0) else 'inactive'}")
        if self.selected_vehicle_id:
            v=self.store.get_vehicle(self.selected_vehicle_id)
            veh=self.store.totals(start,end,self.selected_vehicle_id)
            name=v['nickname'] or ' '.join(x for x in [v['year'],v['make'],v['model']] if x) or v['vin']
            lines += ["", f"Selected vehicle totals: {name}", "-"*60, f"Records: {veh['records']}", f"Labor hours: {veh['labor_hours']:.2f}", f"Labor cost value: ${veh['labor_value']:.2f}", f"Parts total: ${veh['parts_cost']:.2f}", f"Other Work costs: ${veh['other_direct_cost']:.2f}", f"Combined direct costs: ${veh['direct_cost']:.2f}", f"Grand total: ${veh['grand_total']:.2f}"]
        self.set_info("\n".join(lines)+"\n")
        self.status_var.set("Showing profile/totals report.")

    def clear_all_saved_info(self):
        warning = "WARNING: This will permanently delete ALL saved vehicles, notes, maintenance records, other work records, custom links, and profile information." + chr(10) + chr(10) + "Do you want to continue?"
        if not messagebox.askyesno(APP_NAME, warning):
            return
        if messagebox.askyesno(APP_NAME, "Before deleting, do you want to export all saved info first?"):
            self.export_record()
            still_delete = "Export step is finished or was canceled." + chr(10) + chr(10) + "Do you still want to permanently delete ALL saved info?"
            if not messagebox.askyesno(APP_NAME, still_delete):
                return
        confirm = simpledialog.askstring(APP_NAME, "Final warning. Type DELETE to permanently clear ALL saved info, custom links, and profile info:")
        if confirm != "DELETE":
            self.status_var.set("Clear all canceled.")
            return
        self.store.clear_all_data()
        self.selected_vehicle_id = None
        self.vin_var.set("")
        self.set_info("")
        self.selected_vehicle_id = None
        self.vehicle_search_var.set("")
        self.search_var.set("")
        self.vin_var.set("")
        self.search_rows = {}
        self.search.delete(*self.search.get_children())
        self.note_rows=[]; self.notes.delete(0, "end")
        self.mx_rows=[]; self.mx.delete(0, "end")
        self.work_rows=[]; self.work.delete(0, "end")
        self.link_rows=[]; self.links.delete(0, "end")
        self.set_info("")
        self.settings = DEFAULT_SETTINGS.copy()
        ACTIVE_SETTINGS.update(self.settings)
        self.font_size = 9
        self.save_font_size(); self.save_settings()
        self.store.save_app_state({"selected_vehicle_id":"", "vehicle_search":"", "record_search":"", "font_size":"9", "pane_sash_0":"", "pane_sash_1":"", "last_saved_at":nowstamp(), **self.settings})
        self.refresh_all()
        self.status_var.set("Factory reset complete. All saved info, settings, searches, custom links, and profile info were deleted.")
        messagebox.showinfo(APP_NAME, "Factory reset complete. All saved info and settings have been deleted.")

    def edit_vehicle_info(self):
        if not self.selected_vehicle_id:
            sel = self.vehicle_list.curselection()
            if sel:
                self.load_vehicle(self.vehicle_rows[sel[0]]["id"])
        if not self.selected_vehicle_id:
            messagebox.showinfo(APP_NAME, "Select a saved vehicle first.")
            return
        v = self.store.get_vehicle(self.selected_vehicle_id)
        display_vin = "" if str(v["vin"]).startswith("NO-VIN-") else v["vin"]
        fields=[
            ("nickname","Reg Number",v["nickname"]),
            ("vin","VIN (optional)",display_vin),
            ("year","Year",v["year"]),
            ("make","Make",v["make"]),
            ("model","Model",v["model"]),
            ("trim","Trim",v["trim"]),
            ("engine","Engine",v["engine"]),
            ("body","Body/Class",v["body"]),
        ]
        d=EntryDialog(self.root,"Edit Vehicle Info", fields)
        if d.values is not None:
            try:
                self.store.update_vehicle_info(self.selected_vehicle_id, d.values)
                self.refresh_all(); self.load_vehicle(self.selected_vehicle_id)
                self.status_var.set("Updated saved vehicle info.")
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                self.status_var.set(f"Error: {e}")

    def nickname_vehicle(self):
        if not self.selected_vehicle_id: return
        v=self.store.get_vehicle(self.selected_vehicle_id); nick=simpledialog.askstring(APP_NAME,"Vehicle reg number:", initialvalue=v["nickname"])
        if nick is not None: self.store.update_nickname(self.selected_vehicle_id,nick); self.refresh_all()

    def delete_vehicle(self):
        if not self.selected_vehicle_id: return
        if messagebox.askyesno(APP_NAME,"Delete this saved vehicle and all notes/maintenance records?"):
            self.store.delete_vehicle(self.selected_vehicle_id); self.selected_vehicle_id=None; self.set_info(""); self.refresh_all()

    def refresh_notes(self):
        self.note_rows=self.store.notes(self.selected_vehicle_id); self.notes.delete(0,"end")
        for n in self.note_rows:
            shown = n['note'] if n['note'] else "(blank note)"
            self.notes.insert("end", f"{n['created_at']} - {shown[:80]}")

    def add_note(self):
        if not self.selected_vehicle_id: messagebox.showinfo(APP_NAME,"Select or save a vehicle first."); return
        note=simpledialog.askstring(APP_NAME,"Note (date is added automatically; blank is allowed):")
        if note is not None:
            self.store.add_note(self.selected_vehicle_id,note)
            self.refresh_notes(); self.load_vehicle(self.selected_vehicle_id)
            self.status_var.set("Saved note.")

    def edit_note(self):
        sel=self.notes.curselection()
        if not sel: return
        row=self.note_rows[sel[0]]
        note=simpledialog.askstring(APP_NAME,"Edit note:", initialvalue=row["note"])
        if note is not None:
            self.store.update_note(row["id"], note)
            self.refresh_notes(); self.load_vehicle(self.selected_vehicle_id)
            self.status_var.set("Updated note.")

    def delete_note(self):
        sel=self.notes.curselection()
        if sel:
            self.store.delete_note(self.note_rows[sel[0]]["id"])
            self.refresh_notes(); self.load_vehicle(self.selected_vehicle_id)
            self.status_var.set("Deleted note.")

    def refresh_mx(self):
        self.mx_rows=self.store.maintenance(self.selected_vehicle_id)
        self.mx.delete(0, "end")
        for m in self.mx_rows:
            main = m["description"] or m["category"] or "(blank record)"
            extras = []
            if m["mileage"]: extras.append(f"mi {m['mileage']}")
            if m["hours"]: extras.append(f"hrs {m['hours']}")
            part_total = self.store.mx_parts_total(m["id"])
            if part_total: extras.append(f"parts ${part_total:.2f}")
            if m["service_end_date"]: extras.append(f"end {m['service_end_date']}")
            suffix = f" | {' / '.join(extras)}" if extras else ""
            shown_date = m["service_start_date"] or m["service_date"]
            self.mx.insert("end", f"{shown_date} - {main[:90]}{suffix}")

    def require_vehicle_for_record(self):
        if self.selected_vehicle_id:
            return self.selected_vehicle_id
        sel = self.vehicle_list.curselection()
        if sel:
            self.load_vehicle(self.vehicle_rows[sel[0]]["id"])
            return self.selected_vehicle_id
        if len(getattr(self, "vehicle_rows", [])) == 1:
            self.load_vehicle(self.vehicle_rows[0]["id"])
            return self.selected_vehicle_id
        messagebox.showinfo(APP_NAME, "Select a saved vehicle first, then add a Vehicle MX record.")
        return None

    def mx_fields(self, row=None):
        return [("service_start_date","Service start date (DD MMM YYYY)", (row["service_start_date"] or row["service_date"] if row else today_date())), ("service_end_date","Service end date (DD MMM YYYY, optional)", (row["service_end_date"] if row else "")), ("mileage","Mileage", (row["mileage"] if row else "")), ("hours","Engine/equipment hours", (row["hours"] if row else "")), ("category","Category", (row["category"] if row else "Oil/PM/Repair/Inspection")), ("description","Description", (row["description"] if row else "")), ("next_due","Next due (DD MMM YYYY, optional)", (row["next_due"] if row else ""))]

    def clean_numbers(self, vals):
        for k in ("cost","labor_hours"):
            try: vals[k]=float(vals.get(k) or 0)
            except ValueError: vals[k]=0.0
        return vals

    def add_mx(self):
        vid = self.require_vehicle_for_record()
        if not vid: return
        d=MaintenanceDialog(self.root,"Add Maintenance Record",self.mx_fields(), supplier_rows=self.store.links(), technician_rows=self.store.technicians(False), default_technician_id=(self.store.default_technician()["id"] if self.store.default_technician() else None))
        if d.values is not None:
            parts = d.values.pop("structured_parts", [])
            try:
                mx_id = self.store.add_mx(vid,self.clean_numbers(d.values))
                self.store.replace_mx_parts(mx_id, parts)
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                self.status_var.set(f"Error: {e}")
                return
            self.selected_vehicle_id = vid
            self.refresh_mx(); self.refresh_links()
            self.load_vehicle(vid)
            self.status_var.set(f"Saved maintenance record with {len(parts)} part(s). Total Vehicle MX records: {len(self.mx_rows)}")

    def edit_mx(self):
        sel=self.mx.curselection()
        if not sel: return
        idx=sel[0]; row=self.mx_rows[idx]
        existing_parts = [dict(p) for p in self.store.mx_parts(row["id"])]
        d=MaintenanceDialog(self.root,"Edit Maintenance Record",self.mx_fields(row), existing_parts, supplier_rows=self.store.links(), technician_rows=self.store.technicians(False), default_technician_id=(self.store.default_technician()["id"] if self.store.default_technician() else None))
        if d.values is not None:
            parts = d.values.pop("structured_parts", [])
            try:
                self.store.update_mx(row["id"], self.clean_numbers(d.values))
                self.store.replace_mx_parts(row["id"], parts)
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                self.status_var.set(f"Error: {e}")
                return
            self.refresh_mx(); self.refresh_links(); self.load_vehicle(self.selected_vehicle_id)
            self.status_var.set(f"Updated maintenance record with {len(parts)} part(s).")

    def delete_mx(self):
        sel=self.mx.curselection()
        if sel:
            idx=sel[0]; self.store.delete_mx(self.mx_rows[idx]["id"]); self.refresh_mx()
            self.status_var.set("Deleted maintenance record.")

    def refresh_work(self):
        self.work_rows=self.store.work_items() if hasattr(self, "work") else []
        if hasattr(self, "work"):
            self.work.delete(0, "end")
            for w in self.work_rows:
                main = w["title"] or w["description"] or w["category"] or "(blank work)"
                extras = []
                if w["hours"]: extras.append(f"hrs {w['hours']}")
                if w["cost"]: extras.append(f"${w['cost']:.2f}")
                suffix = f" | {' / '.join(extras)}" if extras else ""
                self.work.insert("end", f"{w['work_date']} - {main[:90]}{suffix}")

    def work_fields(self, row=None):
        return [("work_date","Work date (DD MMM YYYY)", (row["work_date"] if row else today_date())), ("title","Title", (row["title"] if row else "")), ("category","Category", (row["category"] if row else "Shop/Fleet/Parts/Admin")), ("description","Description", (row["description"] if row else "")), ("parts","Parts/materials", (row["parts"] if row else "")), ("vendor","Vendor/supplier", (row["vendor"] if row else "")), ("cost","Cost", str(row["cost"] if row else "0")), ("labor_hours","Labor hours", str(row["labor_hours"] if row else "0")), ("hours","Equipment/shop hours", (row["hours"] if row else "")), ("notes","Notes", (row["notes"] if row else ""))]

    def add_work(self):
        d=EntryDialog(self.root,"Add Unlinked Work", self.work_fields())
        if d.values is not None:
            try:
                self.store.add_work(self.clean_numbers(d.values))
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                self.status_var.set(f"Error: {e}")
                return
            self.refresh_work()
            self.status_var.set(f"Saved unlinked work record. Total Other Work records: {len(self.work_rows)}")

    def edit_work(self):
        sel=self.work.curselection()
        if not sel: return
        idx=sel[0]; row=self.work_rows[idx]
        d=EntryDialog(self.root,"Edit Unlinked Work", self.work_fields(row))
        if d.values is not None:
            try:
                self.store.update_work(row["id"], self.clean_numbers(d.values))
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                self.status_var.set(f"Error: {e}")
                return
            self.refresh_work()
            self.status_var.set("Updated unlinked work record.")

    def delete_work(self):
        sel=self.work.curselection()
        if sel and messagebox.askyesno(APP_NAME,"Delete selected unlinked work record?"):
            idx=sel[0]; self.store.delete_work(self.work_rows[idx]["id"]); self.refresh_work()
            self.status_var.set("Deleted unlinked work record.")

    def run_search(self):
        term=self.search_var.get().strip()
        rows=self.store.search_records(term) if term else []
        self.search_rows = {}
        self.search.delete(*self.search.get_children())
        for r in rows:
            veh = r.get("nickname") or r.get("vin") or ""
            iid = self.search.insert("", "end", values=(r.get("kind",""), r.get("rec_date",""), veh, (r.get("text") or "")[:120], f"${float(r.get('cost') or 0):.2f}"))
            self.search_rows[iid] = r

    def open_search_result(self):
        sel = self.search.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a search result first.")
            return
        row = self.search_rows.get(sel[0]) if hasattr(self, "search_rows") else None
        if not row:
            return
        kind = row.get("kind")
        if row.get("vehicle_id"):
            self.load_vehicle(int(row["vehicle_id"]))
        if kind == "Vehicle MX":
            for idx, mx in enumerate(self.mx_rows):
                if mx["id"] == row.get("record_id"):
                    self.mx.selection_clear(0, "end"); self.mx.selection_set(idx); self.mx.see(idx)
                    break
            self.edit_mx()
        elif kind == "Note":
            for idx, note in enumerate(self.note_rows):
                if note["id"] == row.get("record_id"):
                    self.notes.selection_clear(0, "end"); self.notes.selection_set(idx); self.notes.see(idx)
                    break
            self.edit_note()
        elif kind == "Unlinked Work":
            for idx, work in enumerate(self.work_rows):
                if work["id"] == row.get("record_id"):
                    self.work.selection_clear(0, "end"); self.work.selection_set(idx); self.work.see(idx)
                    break
            self.edit_work()
        self.status_var.set(f"Opened search result: {kind}.")

    def show_parts_history(self):
        if not self.selected_vehicle_id:
            messagebox.showinfo(APP_NAME, "Select a saved vehicle first.")
            return
        v = self.store.get_vehicle(self.selected_vehicle_id)
        rows = self.store.parts_history(self.selected_vehicle_id)
        name = v["nickname"] or " ".join(x for x in [v["year"], v["make"], v["model"]] if x) or v["vin"]
        lines = [f"Parts History for {name}", "="*70]
        if rows:
            total = 0.0
            for r in rows:
                total += float(r["total_cost"] or 0)
                lines.append(f"[{r['service_date']}] {r['part_name']}  Part #: {r['part_number']}")
                lines.append(f"  Supplier: {r['supplier']}  Ordered: {r['date_ordered']}  Qty: {float(r['quantity'] or 0):g}  Unit: ${float(r['unit_cost'] or 0):.2f}  Total: ${float(r['total_cost'] or 0):.2f}")
                lines.append(f"  Technician: {r['technician_name']} — {r['technician_rank']} — ${float(r['technician_labor_rate'] or 0):.2f}/hr  Labor hrs: {float(r['labor_hours'] or 0):.2f}  Labor value: ${float(r['labor_value'] or 0):.2f}")
                lines.append(f"  Work: {r['description']}")
                if r['notes']:
                    lines.append(f"  Notes: {r['notes']}")
                lines.append(f"  Entered: {r['created_at']}")
                lines.append("")
            labor_total = sum(float(r["labor_value"] or 0) for r in rows)
            lines.append(f"Total structured parts cost shown: ${total:.2f}")
            lines.append(f"Total itemized labor value shown: ${labor_total:.2f}")
        else:
            lines.append("No parts have been recorded for this vehicle yet.")
        self.set_info("\n".join(lines)+"\n")
        self.status_var.set("Showing selected vehicle parts history.")

    def view_supplier_details(self):
        sel=self.links.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a supplier/source first.")
            return
        l=self.link_rows[sel[0]]
        lines=[
            f"SUPPLIER / SOURCE: {l['title']}",
            "="*70,
            f"Website: {l['url']}",
            f"Point of contact: {l['contact_name']}",
            f"Contact role: {l['contact_title']}",
            f"Email: {l['email']}",
            f"Phone: {l['phone']}",
            f"Address/location: {l['address']}",
            f"Notes: {l['notes']}",
            "",
            "Use Edit Supplier/Source to change this saved information, or Delete Supplier/Source to remove it."
        ]
        self.set_info("\n".join(lines)+"\n")
        self.status_var.set("Showing supplier/source details.")

    def open_link(self):
        sel=self.links.curselection()
        if sel and self.link_rows[sel[0]]["url"]:
            webbrowser.open(self.link_rows[sel[0]]["url"])

    def normalize_url(self, url):
        return normalize_url_text(url)

    def supplier_fields(self, row=None):
        row = row or {}
        return [
            ("title", "Supplier/Source Name", row.get("title", "") if hasattr(row, "get") else row["title"]),
            ("url", "Website URL", row.get("url", "https://") if hasattr(row, "get") else row["url"]),
            ("contact_name", "Point of Contact", row.get("contact_name", "") if hasattr(row, "get") else row["contact_name"]),
            ("contact_title", "Contact Title/Role", row.get("contact_title", "") if hasattr(row, "get") else row["contact_title"]),
            ("email", "Email Address", row.get("email", "") if hasattr(row, "get") else row["email"]),
            ("phone", "Phone Number", row.get("phone", "") if hasattr(row, "get") else row["phone"]),
            ("address", "Address / Location", row.get("address", "") if hasattr(row, "get") else row["address"]),
            ("notes", "Notes", row.get("notes", "") if hasattr(row, "get") else row["notes"]),
        ]

    def add_link(self):
        d=EntryDialog(self.root,"Add Supplier/Source", self.supplier_fields({"url":"https://"}))
        if d.values and d.values.get("title"):
            d.values["url"] = self.normalize_url(d.values.get("url", ""))
            self.store.add_link(d.values)
            self.refresh_links()

    def edit_link(self):
        sel=self.links.curselection()
        if not sel: return
        l=self.link_rows[sel[0]]; d=EntryDialog(self.root,"Edit Supplier/Source", self.supplier_fields(l))
        if d.values and d.values.get("title"):
            d.values["url"] = self.normalize_url(d.values.get("url", ""))
            self.store.update_link(l["id"], d.values)
            self.refresh_links()

    def delete_link(self):
        sel=self.links.curselection()
        if sel and messagebox.askyesno(APP_NAME,"Delete selected supplier/source?"): self.store.delete_link(self.link_rows[sel[0]]["id"]); self.refresh_links()

    def in_range(self, date_text, start, end):
        d = date_sort_key(date_text)
        s = date_sort_key(start) if start else ""
        e = date_sort_key(end) if end else ""
        return (not s or d >= s) and (not e or d <= e)

    def vehicle_sort_name(self, v):
        return (v["nickname"] or " ".join(x for x in [v["year"], v["make"], v["model"]] if x) or v["vin"]).lower()

    def export_record(self):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        d=EntryDialog(self.root,"Export Date Range (optional)", [("start","Start date DD MMM YYYY", ""), ("end","End date DD MMM YYYY", "")])
        start=end=""
        if d.values:
            start=d.values.get("start",""); end=d.values.get("end","")
        target=filedialog.askdirectory(initialdir=str(EXPORT_DIR), title="Choose where to export TXT report")
        if not target:
            self.status_var.set("Export canceled.")
            return
        target=Path(target)
        vehicles=[]
        for v in sorted(self.store.vehicles(), key=self.vehicle_sort_name):
            notes=[dict(x) for x in self.store.notes(v["id"]) if self.in_range(x["created_at"], start, end)]
            mx=[dict(x) for x in self.store.maintenance(v["id"]) if self.in_range(x["service_date"], start, end)]
            vehicles.append({"vehicle":dict(v),"notes":notes,"maintenance":mx})
        work=[dict(x) for x in self.store.work_items() if self.in_range(x["work_date"], start, end)]
        date_stamp = datetime.now().strftime("%Y%m%d-%H%M")
        suffix = f"-{start or 'all'}-to-{end or 'all'}"
        txt=target/f"veh-mx-tracker-report-{date_stamp}{suffix}.txt"
        default_tech = self.store.default_technician()
        totals = self.store.totals(start, end, None)
        lines=[]
        lines.append("VEH MX TRACKER EXPORT")
        lines.append(f"Exported: {nowstamp()}")
        lines.append(f"Date range: {start or 'all'} to {end or 'all'}")
        lines.append("="*90)
        lines.append(f"Default technician: {(default_tech['name'] if default_tech else 'None')}    Rank: {(default_tech['rank'] if default_tech else '')}    Labor rate: ${float(default_tech['labor_rate'] if default_tech else 0):.2f}/hr")
        lines.append(f"Total records: {totals['records']}    Labor hours: {totals['labor_hours']:.2f}    Labor value: ${totals['labor_value']:.2f}    Parts total: ${totals['parts_cost']:.2f}    Other Work costs: ${totals['other_direct_cost']:.2f}    Grand total: ${totals['grand_total']:.2f}")
        technicians = [dict(x) for x in self.store.technicians(include_inactive=True)]
        lines += ["", "TECHNICIANS", "-"*90]
        if technicians:
            for tech in technicians:
                state = "active" if int(tech.get('active') or 0) else "inactive"
                marker = " [default]" if default_tech and tech.get('id') == default_tech['id'] else ""
                lines.append(f"{tech['name']}{marker}")
                lines.append(f"  Rank: {tech['rank']}  Labor rate: ${float(tech['labor_rate'] or 0):.2f}/hr  Status: {state}")
                lines.append(f"  Created: {tech['created_at']}  Updated: {tech['updated_at']}")
        else:
            lines.append("None saved.")
        all_parts = [dict(x) for x in self.store.structured_parts_all(start, end)]
        lines += ["", "ALL ITEMIZED PARTS / LABOR", "-"*90]
        if all_parts:
            for ppart in all_parts:
                vehicle = ppart['nickname'] or ' '.join(x for x in [ppart['year'], ppart['make'], ppart['model']] if x) or ppart['vin']
                lines.append(f"[{ppart['service_date']}] {vehicle} | {ppart['part_name']}")
                lines.append(f"  Maintenance: {ppart['description'] or ppart['category'] or '(blank record)'}")
                lines.append(f"  Part #: {ppart['part_number']}  Supplier: {ppart['supplier']}  Ordered: {ppart['date_ordered']}")
                lines.append(f"  Qty: {float(ppart['quantity'] or 0):g}  Unit: ${float(ppart['unit_cost'] or 0):.2f}  Part total: ${float(ppart['total_cost'] or 0):.2f}")
                lines.append(f"  Technician: {ppart['technician_name']} — {ppart['technician_rank']} — ${float(ppart['technician_labor_rate'] or 0):.2f}/hr")
                lines.append(f"  Labor hrs: {float(ppart['labor_hours'] or 0):.2f}  Labor value: ${float(ppart['labor_value'] or 0):.2f}")
                if ppart['notes']:
                    lines.append(f"  Notes: {ppart['notes']}")
                lines.append("")
        else:
            lines.append("None in selected date range.")
        lines.append("="*90)
        for item in vehicles:
            v=item["vehicle"]
            vin = "NO VIN" if str(v["vin"]).startswith("NO-VIN-") else v["vin"]
            title = v["nickname"] or " ".join(x for x in [v["year"], v["make"], v["model"]] if x) or "Manual Vehicle"
            lines += ["", f"VEHICLE: {title}", "-"*90, f"VIN: {vin}", f"Year/Make/Model: {v['year']} {v['make']} {v['model']}", f"Trim: {v['trim']}", f"Engine: {v['engine']}", f"Body: {v['body']}", f"Created: {v['created_at']}    Updated: {v['updated_at']}"]
            try:
                pub = json.loads(v.get('public_json', '{}') if hasattr(v, 'get') else v['public_json'] or '{}')
            except Exception:
                pub = {}
            if pub:
                counts = pub.get('counts') or {}
                lines += ["", "Saved Local NHTSA Info:", f"  Updated: {pub.get('cached_at','')}", f"  Recalls saved: {counts.get('recalls', len(pub.get('recalls', [])))}  TSB matches saved: {counts.get('tsbs', len(pub.get('tsbs', [])))}  Complaints saved: {counts.get('complaints', len(pub.get('complaints', [])))}"]
            lines += ["", "Maintenance Records:"]
            if item["maintenance"]:
                for m in item["maintenance"]:
                    part_rows = [dict(p) for p in self.store.mx_parts(m['id'])]
                    parts_total = sum(float(p.get('total_cost') or 0) for p in part_rows)
                    labor_total = sum(float(p.get('labor_value') or 0) for p in part_rows)
                    labor_hours = sum(float(p.get('labor_hours') or 0) for p in part_rows)
                    lines.append(f"  [{m['service_date']}] {m['description'] or m['category'] or '(blank record)'}")
                    lines.append(f"    Mileage: {m['mileage']}  Hours: {m['hours']}  Category: {m['category']}  Parts total: ${parts_total:.2f}  Labor hrs: {labor_hours:.2f}  Labor value: ${labor_total:.2f}")
                    if part_rows:
                        lines.append("    Itemized parts/labor:")
                        for ppart in part_rows:
                            lines.append(f"      - {ppart['part_name']}  Part #: {ppart['part_number']}  Supplier: {ppart['supplier']}  Ordered: {ppart['date_ordered']}  Qty: {float(ppart['quantity'] or 0):g}  Unit: ${float(ppart['unit_cost'] or 0):.2f}  Part total: ${float(ppart['total_cost'] or 0):.2f}")
                            lines.append(f"        Technician: {ppart.get('technician_name','')} — {ppart.get('technician_rank','')} — ${float(ppart.get('technician_labor_rate') or 0):.2f}/hr  Labor hrs: {float(ppart.get('labor_hours') or 0):.2f}  Labor value: ${float(ppart.get('labor_value') or 0):.2f}")
                    else:
                        lines.append("    Itemized parts: none recorded")
                    lines.append(f"    Next due: {m['next_due']}")
                    lines.append(f"    Created: {m['created_at']}  Updated: {m['updated_at']}")
            else:
                lines.append("  None in selected date range.")
            lines += ["", "Notes:"]
            if item["notes"]:
                for n in item["notes"]: lines.append(f"  [{n['created_at']}] {n['note'] or '(blank note)'}")
            else:
                lines.append("  None in selected date range.")
        lines += ["", "="*90, "UNLINKED / OTHER WORK", "-"*90]
        if work:
            for witem in work:
                lines.append(f"[{witem['work_date']}] {witem['title'] or witem['description'] or '(blank work)'}")
                lines.append(f"  Category: {witem['category']}  Cost: ${float(witem['cost'] or 0):.2f}  Labor hrs: {float(witem['labor_hours'] or 0):.2f}  Hours: {witem['hours']}")
                lines.append(f"  Description: {witem['description']}")
                lines.append(f"  Parts: {witem['parts']}  Vendor: {witem['vendor']}")
                lines.append(f"  Notes: {witem['notes']}")
                lines.append(f"  Created: {witem['created_at']}  Updated: {witem['updated_at']}")
                lines.append("")
        else:
            lines.append("None in selected date range.")
        suppliers = [dict(x) for x in self.store.links()]
        lines += ["", "="*90, "SUPPLIERS / SOURCES", "-"*90]
        if suppliers:
            for sup in suppliers:
                lines.append(sup["title"])
                lines.append(f"  Website: {sup['url']}")
                lines.append(f"  Point of contact: {sup['contact_name']}  Role: {sup['contact_title']}")
                lines.append(f"  Email: {sup['email']}  Phone: {sup['phone']}")
                lines.append(f"  Address/location: {sup['address']}")
                lines.append(f"  Notes: {sup['notes']}")
                lines.append("")
        else:
            lines.append("None saved.")
        txt.write_text("\n".join(lines)+"\n")
        self.status_var.set(f"Exported one complete TXT report to {target}")
        messagebox.showinfo(APP_NAME, f"Exported one complete TXT report:\n{txt}")


def main():
    root=tk.Tk(); App(root); root.mainloop()
if __name__ == "__main__": main()
