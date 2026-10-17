# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from postgrid_integration import install
from postgrid_integration.tests.utils import rollback_after_test


def setter_value(doctype: str, fieldname: str) -> str | None:
	value = frappe.db.get_value(
		"Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": "options"}, "value"
	)
	return str(value) if value is not None else None


def setter_options(doctype: str, fieldname: str) -> list[str]:
	value = setter_value(doctype, fieldname)
	return value.split("\n") if value else []


def workspace_state() -> tuple[list[tuple[str, str | None]], list[str]]:
	workspace = frappe.get_doc("Workspace", "Integrations")
	links = [
		(link.type, link.link_to)
		for link in workspace.get("links")
		if link.label in ("Direct Mail", "PostGrid Settings")
	]
	cards = [
		block["data"].get("card_name")
		for block in json.loads(workspace.get("content"))
		if block["type"] == "card"
	]
	return links, cards


class TestInstall(IntegrationTestCase):
	def setUp(self):
		# Each test starts from the installed state
		rollback_after_test(self)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# The tests change the options' property setters; drop the metas built from them afterwards
		cls.addClassCleanup(frappe.clear_cache, doctype="Notification")
		cls.addClassCleanup(frappe.clear_cache, doctype="Communication")

	def test_installed(self):
		# A new site gets the card, the link and the mail channels from after_install
		links, cards = workspace_state()
		self.assertEqual(links, [("Card Break", None), ("Link", "PostGrid Settings")])
		self.assertIn("Direct Mail", cards)
		self.assertIn("Mailed Letter", setter_options("Notification", "channel"))
		self.assertIn("Mailed Letter", setter_options("Communication", "communication_type"))

	def test_uninstall_then_install(self):
		install.before_uninstall()
		links, cards = workspace_state()
		self.assertEqual(links, [])
		self.assertNotIn("Direct Mail", cards)
		# the setters only ever added the mail channels, so they go
		self.assertIsNone(setter_value("Notification", "channel"))
		self.assertIsNone(setter_value("Communication", "communication_type"))

		# Uninstalling twice finds nothing to do
		install.before_uninstall()

		install.after_install()
		links, cards = workspace_state()
		self.assertEqual(links, [("Card Break", None), ("Link", "PostGrid Settings")])
		self.assertEqual(cards.count("Direct Mail"), 1)
		channels = setter_options("Notification", "channel")
		# frappe's own options keep their order, and the mail channel comes last
		self.assertEqual(channels[0], "Email")
		self.assertEqual(channels[-1], "Mailed Letter")

	def test_migrate_adds_to_an_existing_setter(self):
		frappe.db.set_value(
			"Property Setter",
			{"doc_type": "Notification", "field_name": "channel", "property": "options"},
			"value",
			"Email\nSlack\nCarrier Pigeon",
		)
		install.after_migrate()
		self.assertEqual(
			setter_value("Notification", "channel"), "Email\nSlack\nCarrier Pigeon\nMailed Letter"
		)
		# and is idempotent
		install.after_migrate()
		self.assertEqual(
			setter_value("Notification", "channel"), "Email\nSlack\nCarrier Pigeon\nMailed Letter"
		)

		# Uninstalling keeps another app's option and the setter that holds it
		install.before_uninstall()
		self.assertEqual(setter_value("Notification", "channel"), "Email\nSlack\nCarrier Pigeon")

	def test_unknown_field_is_skipped(self):
		install.add_field_options("Notification", "no_such_field", ["Mailed Letter"])
		install.revert_field_options("Notification", "no_such_field", ["Mailed Letter"])
		self.assertIsNone(setter_value("Notification", "no_such_field"))

	def test_card_with_other_links_stays(self):
		install.add_workspace_card_link(
			"Integrations", "Direct Mail", "DocType", "Integration Request", "Requests"
		)
		install.remove_workspace_card_link("Integrations", "Direct Mail", "PostGrid Settings")
		links, cards = workspace_state()
		self.assertEqual(links, [("Card Break", None)])
		self.assertIn("Direct Mail", cards)

	def test_missing_workspace(self):
		install.remove_workspace_card_link("No Such Workspace", "Direct Mail", "PostGrid Settings")
