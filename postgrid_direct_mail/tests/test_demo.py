# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

"""The demo hook frappe-demo calls (`postgrid_direct_mail.demo.setup`)."""

import datetime
from unittest.mock import patch

import frappe
import postgrid
from frappe.tests import IntegrationTestCase

from postgrid_direct_mail import demo
from postgrid_direct_mail.install import after_migrate

CTX = {"today": datetime.date(2026, 1, 15), "seed": 1, "company": None, "erpnext_demo": False}


class TestDemo(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# The Mailed Letter channel and communication type, as a migrated site has them
		after_migrate()
		frappe.clear_cache(doctype="Notification")
		frappe.clear_cache(doctype="Communication")

	def test_setup_submits_and_mails_the_statements(self):
		with patch.object(postgrid.Letter, "create") as create:
			demo.setup(CTX)
		# the demo's own stand-in answers, never the real client
		create.assert_not_called()

		for name, *_ in demo.STATEMENTS:
			self.assertEqual(frappe.db.get_value(demo.DOCTYPE, name, "docstatus"), 1)
		self.assertEqual(
			frappe.db.get_value("Customer Statement", "STMT-0003", "due_date"), datetime.date(2026, 1, 31)
		)

		mailed = frappe.get_all(
			"Communication",
			filters={"reference_doctype": demo.DOCTYPE, "communication_type": "Mailed Letter"},
			fields=["reference_name", "delivery_status", "communication_date"],
			order_by="reference_name",
		)
		self.assertEqual(
			[(row.reference_name, row.delivery_status) for row in mailed],
			[("STMT-0001", "Opened"), ("STMT-0002", "Sent")],
		)
		self.assertEqual(mailed[1].communication_date.date(), datetime.date(2026, 1, 11))
		self.assertEqual(
			frappe.db.get_value("Integration Request", {"request_id": "letter_demo_stmt_0002"}, "status"),
			"Completed",
		)

		self.assertEqual(frappe.db.get_value("Notification", demo.NOTIFICATION, "channel"), "Mailed Letter")
		self.assertEqual(frappe.db.get_single_value("PostGrid Settings", "mode"), "Test")

	def test_setup_is_idempotent(self):
		demo.setup(CTX)
		demo.setup(CTX)
		self.assertEqual(frappe.db.count(demo.DOCTYPE), len(demo.STATEMENTS))
		self.assertEqual(
			frappe.db.count(
				"Communication", {"reference_doctype": demo.DOCTYPE, "communication_type": "Mailed Letter"}
			),
			len(demo.MAILED),
		)
		self.assertEqual(frappe.db.count("Address", {"address_title": "Harbor Supply Co."}), 1)
		self.assertEqual(frappe.db.count("Contact", {"first_name": "Dana", "last_name": "Whitfield"}), 1)
