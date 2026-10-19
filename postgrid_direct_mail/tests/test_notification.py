# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.email.doctype.notification.notification import Notification
from frappe.tests import IntegrationTestCase

from postgrid_direct_mail.install import after_migrate
from postgrid_direct_mail.postgrid_integration.hooks.notification import DirectMailNotification
from postgrid_direct_mail.tests.utils import make_address, rollback_after_test

MAIL_LETTER = "postgrid_direct_mail.postgrid_integration.hooks.notification.mail_letter"


class TestDirectMailNotification(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# The Mailed Letter channel, as a migrated site has it
		after_migrate()
		frappe.clear_cache(doctype="Notification")
		cls.addClassCleanup(frappe.clear_cache, doctype="Notification")

	def setUp(self):
		rollback_after_test(self)
		if not frappe.db.exists("Print Format", "PostGrid Cover Letter"):
			frappe.get_doc(
				{
					"doctype": "Print Format",
					"name": "PostGrid Cover Letter",
					"doc_type": "Contact",
					"module": "PostGrid Integration",
					"standard": "No",
					"custom_format": 1,
					"print_format_type": "Jinja",
					"html": "<p>Dear {{ doc.first_name }}</p>",
				}
			).insert(ignore_permissions=True)
		self.from_address = make_address("Avunu LLC")
		self.to_address = make_address("Customer Inc")
		mail_letter = patch(MAIL_LETTER)
		self.mail_letter = mail_letter.start()
		self.addCleanup(mail_letter.stop)

	def make_notification(self, **values):
		notification = frappe.get_doc(
			{
				"doctype": "Notification",
				"name": values.pop("name", frappe.generate_hash(length=10)),
				"document_type": "Contact",
				"event": "New",
				"channel": "Mailed Letter",
				"from_address": self.from_address,
				"to_address_document_field": "address",
				"address_placement": "Top of First Page",
				"envelope_type": "Flat",
				"color": 1,
				"double_sided": 0,
				"express": 1,
				"enabled": 1,
				**values,
			}
		).insert(ignore_permissions=True)
		return notification

	def make_contact(self, address=None):
		return frappe.get_doc(
			{"doctype": "Contact", "first_name": "Grace", "last_name": "Hopper", "address": address}
		).insert(ignore_permissions=True)

	def test_extends_the_notification_controller(self):
		notification = self.make_notification()
		self.assertIsInstance(notification, DirectMailNotification)
		self.assertIsInstance(notification, Notification)

	def test_mails_on_frappe_notification_run(self):
		self.make_notification(cl_print_format="PostGrid Cover Letter", with_cover_letter=1)
		contact = self.make_contact(self.to_address)

		self.mail_letter.assert_called_once()
		kwargs = self.mail_letter.call_args.kwargs
		self.assertEqual(kwargs["doctype"], "Contact")
		self.assertEqual(kwargs["docname"], contact.name)
		self.assertIsNone(kwargs["print_format"])
		self.assertEqual(kwargs["from_address"], self.from_address)
		self.assertEqual(kwargs["to_address"], self.to_address)
		self.assertIsNone(kwargs["to_contact"])
		self.assertEqual(kwargs["cl_print_format"], "PostGrid Cover Letter")
		self.assertEqual(
			kwargs["pg_parameters"],
			{
				"address_placement": "top_first_page",
				"envelope_type": "flat",
				"misc": {"color": 1, "double_sided": 0, "express": 1},
			},
		)

	def test_save_event(self):
		self.make_notification(event="Save", with_cover_letter=0, cl_print_format="PostGrid Cover Letter")
		contact = self.make_contact(self.to_address)
		self.mail_letter.reset_mock()
		contact.save()
		self.mail_letter.assert_called_once()
		self.assertIsNone(self.mail_letter.call_args.kwargs["cl_print_format"])

	def test_other_channels_are_left_to_frappe(self):
		notification = self.make_notification(
			channel="System Notification",
			subject="Hello",
			recipients=[{"receiver_by_role": "System Manager"}],
		)
		contact = self.make_contact(self.to_address)
		with patch.object(Notification, "send_notification_by_channel") as base:
			notification.send_notification_by_channel(contact, {})
		self.mail_letter.assert_not_called()
		base.assert_called_once_with(contact, {})

	def test_mailed_letter_still_reaches_frappe(self):
		# frappe still gets the call, for the optional system notification
		notification = self.make_notification(enabled=0)
		contact = self.make_contact(self.to_address)
		with patch.object(Notification, "send_notification_by_channel") as base:
			notification.send_notification_by_channel(contact, {})
		self.mail_letter.assert_called_once()
		base.assert_called_once_with(contact, {})

	def test_events_that_mail(self):
		notification = self.make_notification(enabled=0)
		for event in ("New", "Save", "Submit", "Cancel", "Days Before", "Days After"):
			notification.event = event
			self.assertTrue(notification.mails_on_event(), event)
		for event in ("Value Change", "Minutes Before", "Minutes After"):
			notification.event = event
			self.assertFalse(notification.mails_on_event(), event)
		notification.event = "Method"
		notification.method = "on_update"
		self.assertTrue(notification.mails_on_event())
		notification.method = "custom_method"
		self.assertFalse(notification.mails_on_event())

	def test_value_change_does_not_mail(self):
		self.make_notification(event="Value Change", value_changed="first_name")
		contact = self.make_contact(self.to_address)
		contact.first_name = "Amazing Grace"
		contact.save()
		self.mail_letter.assert_not_called()

	def test_pg_parameters(self):
		notification = self.make_notification(
			enabled=0, address_placement="Insert Blank Page", envelope_type="Standard Double Window"
		)
		params = notification.get_pg_parameters()
		self.assertEqual(params["address_placement"], "insert_blank_page")
		self.assertEqual(params["envelope_type"], "standard_double_window")

	def test_missing_address_is_logged(self):
		notification = self.make_notification(enabled=0)
		contact = self.make_contact()
		with patch("frappe.log_error") as log_error:
			notification.mail_document(contact)
		self.mail_letter.assert_not_called()
		self.assertEqual(log_error.call_args.kwargs["title"], "Failed to mail notification")

	def test_mail_failure_is_logged(self):
		notification = self.make_notification(enabled=0, to_contact_document_field="address")
		contact = self.make_contact(self.to_address)
		self.mail_letter.side_effect = frappe.ValidationError("PostGrid is down")
		with patch("frappe.log_error") as log_error:
			notification.mail_document(contact)
		self.assertEqual(self.mail_letter.call_args.kwargs["to_contact"], self.to_address)
		self.assertIn("PostGrid is down", log_error.call_args.kwargs["message"])
