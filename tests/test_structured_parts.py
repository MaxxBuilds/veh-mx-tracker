import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import veh_mx_tracker as app


class StructuredPartsTests(unittest.TestCase):
    def make_store(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = Path(self.tmp.name) / "config"
        patches = [
            mock.patch.object(app, "CONFIG_DIR", config),
            mock.patch.object(app, "DB_PATH", config / "vehicles.sqlite3"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return app.Store()

    def add_vehicle_and_mx(self, store):
        vid = store.save_vehicle(
            "1HGCM82633A004352",
            {"ModelYear": "2003", "Make": "HONDA", "Model": "Accord"},
            "TEST-001",
        )
        mx_id = store.add_mx(
            vid,
            {
                "service_start_date": "30 May 2026",
                "service_end_date": "",
                "mileage": "123456",
                "hours": "",
                "category": "Oil / Lube",
                "description": "Oil service",
                "labor_hours": 1.25,
                "next_due": "",
            },
        )
        return vid, mx_id

    def test_structured_parts_are_linked_to_maintenance_and_have_their_own_total(self):
        store = self.make_store()
        vid, mx_id = self.add_vehicle_and_mx(store)

        part_id = store.add_mx_part(
            mx_id,
            {
                "part_name": "Oil filter",
                "part_number": "FIL-2003-HON-001",
                "supplier": "DEMO - NAPA Fleet Parts",
                "date_ordered": "28 May 2026",
                "quantity": 2,
                "unit_cost": 11.49,
                "notes": "Demo structured part",
            },
        )

        parts = [dict(p) for p in store.mx_parts(mx_id)]
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["id"], part_id)
        self.assertEqual(parts[0]["maintenance_id"], mx_id)
        self.assertEqual(parts[0]["part_name"], "Oil filter")
        self.assertEqual(parts[0]["part_number"], "FIL-2003-HON-001")
        self.assertEqual(parts[0]["supplier"], "DEMO - NAPA Fleet Parts")
        self.assertEqual(parts[0]["date_ordered"], "28 May 2026")
        self.assertEqual(parts[0]["quantity"], 2)
        self.assertEqual(parts[0]["unit_cost"], 11.49)
        self.assertEqual(parts[0]["total_cost"], 22.98)

        mx = store.maintenance(vid)[0]
        self.assertNotIn("cost", mx.keys())
        self.assertNotIn("parts", mx.keys())
        self.assertEqual(store.mx_parts_total(mx_id), 22.98)
        store.db.close()

    def test_dashboard_counts_structured_part_names_without_prices(self):
        store = self.make_store()
        _, mx_id = self.add_vehicle_and_mx(store)
        store.add_mx_part(mx_id, {"part_name": "Oil filter", "part_number": "FIL-1", "supplier": "A", "date_ordered": "28 May 2026", "quantity": 1, "unit_cost": 11.49, "notes": ""})
        store.add_mx_part(mx_id, {"part_name": "Oil filter", "part_number": "FIL-2", "supplier": "B", "date_ordered": "29 May 2026", "quantity": 3, "unit_cost": 12.00, "notes": ""})

        data = store.dashboard_data()
        self.assertEqual(data["parts"]["Oil filter"], 2)
        self.assertTrue(all("$" not in part for part in data["parts"]))
        store.db.close()

    def test_export_parts_csv_writes_structured_part_rows(self):
        store = self.make_store()
        _, mx_id = self.add_vehicle_and_mx(store)
        store.add_mx_part(mx_id, {"part_name": "Cabin filter", "part_number": "CAB-DEMO-002", "supplier": "DEMO - OEM Parts Desk", "date_ordered": "27 May 2026", "quantity": 1, "unit_cost": 28.50, "notes": "CSV demo"})

        out = Path(self.tmp.name) / "parts.csv"
        store.export_parts_csv(out, "", "")
        with out.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["part_name"], "Cabin filter")
        self.assertEqual(rows[0]["part_number"], "CAB-DEMO-002")
        self.assertEqual(rows[0]["supplier"], "DEMO - OEM Parts Desk")
        self.assertEqual(rows[0]["date_ordered"], "27 May 2026")
        store.db.close()

    def test_strict_date_format_rejects_iso_and_normalizes_month_case(self):
        self.assertEqual(app.normalize_date_input("30 May 2026", "Service start date"), "30 May 2026")
        self.assertEqual(app.normalize_date_input("30 may 2026", "Service start date"), "30 May 2026")
        with self.assertRaisesRegex(ValueError, "Service start date must use DD MMM YYYY format"):
            app.normalize_date_input("2026-05-30", "Service start date")

    def test_maintenance_records_use_service_start_and_manual_service_end(self):
        store = self.make_store()
        vid, mx_id = self.add_vehicle_and_mx(store)
        store.update_mx(mx_id, {
            "service_start_date": "30 May 2026",
            "service_end_date": "31 May 2026",
            "mileage": "123456",
            "hours": "",
            "category": "Oil / Lube",
            "description": "Oil service complete",
            "vendor": "",
            "labor_hours": 1.25,
            "next_due": "01 Jun 2026",
        })
        mx = dict(store.maintenance(vid)[0])
        self.assertEqual(mx["service_start_date"], "30 May 2026")
        self.assertEqual(mx["service_end_date"], "31 May 2026")
        self.assertEqual(mx["service_date"], "30 May 2026")
        store.db.close()

    def test_maintenance_table_has_no_legacy_parts_cost_or_vendor_columns(self):
        store = self.make_store()
        columns = [row[1] for row in store.db.execute("PRAGMA table_info(maintenance)").fetchall()]
        self.assertNotIn("parts", columns)
        self.assertNotIn("cost", columns)
        self.assertNotIn("vendor", columns)
        self.assertNotIn("labor_hours", columns)
        store.db.close()

    def test_maintenance_dialog_fields_hide_legacy_parts_cost_and_vendor(self):
        ui = app.App.__new__(app.App)
        fields = ui.mx_fields()
        keys = [field[0] for field in fields]
        self.assertNotIn("parts", keys)
        self.assertNotIn("cost", keys)
        self.assertNotIn("vendor", keys)
        self.assertNotIn("labor_hours", keys)

    def test_manual_part_supplier_populates_supplier_sources_with_available_info(self):
        store = self.make_store()
        _, mx_id = self.add_vehicle_and_mx(store)
        store.add_mx_part(mx_id, {
            "part_name": "Battery",
            "supplier": "Fleet Battery House",
            "supplier_url": "fleetbattery.example",
            "supplier_contact_name": "Parts Desk",
            "supplier_contact_title": "Counter",
            "supplier_email": "parts@example.test",
            "supplier_phone": "555-0100",
            "supplier_address": "Bay 2",
            "supplier_notes": "Open Saturdays",
            "date_ordered": "30 May 2026",
            "quantity": 1,
            "unit_cost": 199.99,
            "notes": "manual supplier",
        })
        links = [dict(x) for x in store.links() if x["title"] == "Fleet Battery House"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["url"], "https://fleetbattery.example")
        self.assertEqual(links[0]["contact_name"], "Parts Desk")
        self.assertEqual(links[0]["contact_title"], "Counter")
        self.assertEqual(links[0]["email"], "parts@example.test")
        self.assertEqual(links[0]["phone"], "555-0100")
        self.assertEqual(links[0]["address"], "Bay 2")
        self.assertEqual(links[0]["notes"], "Open Saturdays")
        store.db.close()

    def test_profile_converts_to_default_technician_and_parts_store_labor_snapshot(self):
        store = self.make_store()
        tech = dict(store.default_technician())
        self.assertEqual(tech["name"], "Default Technician")
        store.update_technician(tech["id"], {"name": "Maxx", "rank": "Lead", "labor_rate": 50, "active": "1"})
        vid, mx_id = self.add_vehicle_and_mx(store)
        store.add_mx_part(mx_id, {"part_name": "Brake pads", "technician_id": tech["id"], "date_ordered": "30 May 2026", "quantity": 1, "unit_cost": 40, "labor_hours": 1.5})
        part = dict(store.mx_parts(mx_id)[0])
        self.assertEqual(part["technician_name"], "Maxx")
        self.assertEqual(part["technician_rank"], "Lead")
        self.assertEqual(part["technician_labor_rate"], 50)
        self.assertEqual(part["labor_hours"], 1.5)
        self.assertEqual(part["labor_value"], 75)
        totals = store.totals("", "", vid)
        self.assertEqual(totals["labor_hours"], 1.5)
        self.assertEqual(totals["labor_value"], 75)
        store.db.close()

    def test_legacy_parent_labor_migrates_to_legacy_labor_part(self):
        store = self.make_store()
        tech = dict(store.default_technician())
        store.update_technician(tech["id"], {"name": "Default Tech", "rank": "A", "labor_rate": 25, "active": "1"})
        vid, mx_id = self.add_vehicle_and_mx(store)
        store.db.execute("ALTER TABLE maintenance ADD COLUMN labor_hours REAL DEFAULT 0")
        store.db.execute("UPDATE maintenance SET labor_hours=2.5 WHERE id=?", (mx_id,))
        store.db.commit()
        store.db.close()
        reopened = app.Store()
        columns = [row[1] for row in reopened.db.execute("PRAGMA table_info(maintenance)").fetchall()]
        self.assertNotIn("labor_hours", columns)
        parts = [dict(p) for p in reopened.mx_parts(mx_id) if p["part_name"] == "Legacy labor"]
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["technician_name"], "Default Tech")
        self.assertEqual(parts[0]["labor_hours"], 2.5)
        self.assertEqual(parts[0]["labor_value"], 62.5)
        reopened.db.close()

    def test_legacy_parent_parts_vendor_cost_migrates_to_structured_part(self):
        store = self.make_store()
        vid, mx_id = self.add_vehicle_and_mx(store)
        store.db.execute("ALTER TABLE maintenance ADD COLUMN parts TEXT DEFAULT ''")
        store.db.execute("ALTER TABLE maintenance ADD COLUMN vendor TEXT DEFAULT ''")
        store.db.execute("ALTER TABLE maintenance ADD COLUMN cost REAL DEFAULT 0")
        store.db.execute(
            "UPDATE maintenance SET parts=?, vendor=?, cost=? WHERE id=?",
            ("Oil filter; Drain plug washer", "Fleet Parts Counter", 37.49, mx_id),
        )
        store.db.commit()
        store.db.close()

        reopened = app.Store()
        columns = [row[1] for row in reopened.db.execute("PRAGMA table_info(maintenance)").fetchall()]
        self.assertNotIn("parts", columns)
        self.assertNotIn("cost", columns)
        self.assertNotIn("vendor", columns)
        migrated = [dict(p) for p in reopened.mx_parts(mx_id) if p["notes"].startswith("Migrated from parent maintenance parts/cost/vendor.")]
        self.assertEqual(len(migrated), 1)
        self.assertEqual(migrated[0]["part_name"], "Oil filter")
        self.assertEqual(migrated[0]["supplier"], "Fleet Parts Counter")
        self.assertEqual(migrated[0]["quantity"], 1)
        self.assertEqual(migrated[0]["unit_cost"], 37.49)
        self.assertEqual(migrated[0]["total_cost"], 37.49)
        self.assertIn("Drain plug washer", migrated[0]["notes"])
        reopened.db.close()

    def test_export_txt_is_single_complete_document_without_extra_parts_csv_prompt(self):
        source = (ROOT / "veh_mx_tracker.py").read_text()
        self.assertNotIn("Also export itemized maintenance parts as a CSV file", source)
        self.assertIn("ALL ITEMIZED PARTS / LABOR", source)
        self.assertIn("TECHNICIANS", source)
        self.assertIn("SUPPLIERS / SOURCES", source)
        self.assertIn("Exported one complete TXT report", source)


if __name__ == "__main__":
    unittest.main()
