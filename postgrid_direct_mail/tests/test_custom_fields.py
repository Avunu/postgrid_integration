# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

import json
from pathlib import Path

import frappe
from frappe.custom.doctype.customize_form.customize_form import reset_customization
from frappe.modules.utils import sync_customizations
from frappe.tests import IntegrationTestCase

from postgrid_direct_mail import install
from postgrid_direct_mail.setup.custom_fields import get_custom_fields
from postgrid_direct_mail.tests.utils import rollback_after_test, skip_schema_sync

CUSTOM_DIR = Path(__file__).resolve().parent.parent / "postgrid_integration" / "custom"


def shipped_keys() -> set[tuple[str, str]]:
	return {
		(doctype, fieldname)
		for doctype, fieldnames in get_custom_fields().items()
		for fieldname in fieldnames
	}


def field_rows() -> dict[tuple[str, str], frappe._dict]:
	rows = frappe.get_all(
		"Custom Field",
		filters={"dt": ("in", list(get_custom_fields()))},
		fields=["name", "dt", "fieldname", "is_system_generated", "modified"],
	)
	return {(row.dt, row.fieldname): row for row in rows if (row.dt, row.fieldname) in shipped_keys()}


def clear_flag(doctype: str, fieldname: str) -> None:
	"""What a site that migrated with `"is_system_generated": 0` in custom/*.json has."""
	frappe.db.set_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "is_system_generated", 0)


class TestCustomFields(IntegrationTestCase):
	def setUp(self):
		rollback_after_test(self)
		skip_schema_sync(self)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for doctype in ("Address", "Notification"):
			cls.addClassCleanup(frappe.clear_cache, doctype=doctype)

	def assert_installed(self) -> None:
		rows = field_rows()
		self.assertEqual(set(rows), shipped_keys())
		for key, row in rows.items():
			self.assertEqual(row.is_system_generated, 1, key)
		self.assertTrue(frappe.get_meta("Address").get_field("postgrid_id").is_system_generated)
		self.assertTrue(frappe.get_meta("Notification").get_field("from_address").is_system_generated)

	def test_shipped_fields(self):
		fields = get_custom_fields()
		self.assertEqual(fields["Address"], ["postgrid_id"])
		self.assertEqual(len(fields["Notification"]), 13)
		self.assertIn("cl_print_format", fields["Notification"])

	def test_installed_as_system_generated(self):
		self.assert_installed()

	def test_migrate_restores_the_flag(self):
		clear_flag("Address", "postgrid_id")
		clear_flag("Notification", "express")
		install.after_migrate()
		self.assert_installed()

	def test_install_flags_the_synced_fields(self):
		# what install_app does: after_install, then frappe's customisation sync, then after_sync
		clear_flag("Address", "postgrid_id")
		install.after_install()
		sync_customizations("postgrid_direct_mail")
		install.after_sync()
		self.assert_installed()

	def test_migrate_is_idempotent(self):
		before = field_rows()
		install.after_migrate()
		install.after_migrate()
		self.assertEqual(field_rows(), before)

	def test_sync_keeps_the_flag(self):
		# frappe's own customisation sync (bench migrate, before after_migrate) leaves the flag alone,
		# because the files don't name it
		sync_customizations("postgrid_direct_mail")
		self.assert_installed()

	def test_new_field_from_sync_gets_the_flag(self):
		# a field the sync inserts comes in with the flag off; after_migrate turns it on
		frappe.db.delete("Custom Field", {"dt": "Notification", "fieldname": "cl_print_format"})
		sync_customizations("postgrid_direct_mail")
		self.assertEqual(
			frappe.db.get_value(
				"Custom Field", {"dt": "Notification", "fieldname": "cl_print_format"}, "is_system_generated"
			),
			0,
		)
		install.after_migrate()
		self.assert_installed()

	def test_reset_to_standard_keeps_them(self):
		for doctype in ("Address", "Notification"):
			reset_customization(doctype)
		self.assert_installed()

	def test_uninstall_removes_only_ours(self):
		# Just the row: inserting through the controller would add a column, and DDL commits
		other = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"name": "Notification-pg_test_other_app",
				"dt": "Notification",
				"fieldname": "pg_test_other_app",
				"fieldtype": "Data",
				"label": "Another App's Field",
				"insert_after": "cl_print_format",
			}
		)
		other.db_insert()

		install.before_uninstall()
		self.assertEqual(field_rows(), {})
		self.assertIsNone(frappe.get_meta("Notification").get_field("from_address"))
		self.assertIsNone(frappe.get_meta("Address").get_field("postgrid_id"))
		self.assertTrue(frappe.db.exists("Custom Field", other.name))
		# uninstalling twice finds nothing to do
		install.before_uninstall()

	def test_customization_files_pass_validate_customizations(self):
		# What test_utils' validate_customizations checks on these files (it runs only in a bench)
		for path in sorted(CUSTOM_DIR.glob("*.json")):
			data = json.loads(path.read_text())
			for row in data.get("custom_fields", []) + data.get("property_setters", []):
				self.assertNotIn("is_system_generated", row, path.name)
				self.assertEqual(row.get("module"), "PostGrid Integration", path.name)
