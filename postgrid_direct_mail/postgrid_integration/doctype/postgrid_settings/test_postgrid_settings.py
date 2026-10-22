# Copyright (c) 2024, Avunu LLC and Contributors
# See license.txt

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
import jwt
import postgrid
from frappe.tests import IntegrationTestCase

from postgrid_direct_mail.postgrid_integration.doctype import postgrid_settings as api
from postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.postgrid_settings import (
	PostGridSettings,
	reset_webhooks,
)
from postgrid_direct_mail.tests.utils import (
	count_pages,
	make_address,
	make_contact,
	make_letter,
	make_pdf,
	make_request,
	rollback_after_test,
	set_settings,
)

SECRET = "webhook-secret"


def get_settings() -> PostGridSettings:
	settings = frappe.get_doc("PostGrid Settings")
	assert isinstance(settings, PostGridSettings)
	return settings


class TestPostGridSettings(IntegrationTestCase):
	def setUp(self):
		rollback_after_test(self)
		set_settings(
			mode="Test",
			pm_key_test="test_sk_key",
			pm_key_live="live_sk_key",
			webhooks_secret=None,
			webhook_id_test=None,
			webhook_id_live=None,
		)
		postgrid.pm_key = None

	def test_loading_needs_no_key(self):
		# A new site has no mode and no keys; loading the settings must not reach for either
		frappe.db.set_single_value("PostGrid Settings", "mode", None)
		settings = get_settings()
		self.assertIsNone(postgrid.pm_key)
		self.assertTrue(settings.webhook_url.endswith("postgrid_settings.webhooks"))

	def test_mode_is_required(self):
		settings = get_settings()
		settings.set("mode", None)
		with self.assertRaises(frappe.MandatoryError):
			settings.save()

	def test_initialize_client_uses_the_mode_key(self):
		settings = get_settings()
		self.assertIs(settings.initialize_client(), postgrid)
		self.assertEqual(postgrid.pm_key, "test_sk_key")
		settings.mode = "Live"
		settings.initialize_client()
		self.assertEqual(postgrid.pm_key, "live_sk_key")

	def test_validate_creates_secret_and_webhook(self):
		with patch.object(postgrid.Webhook, "create", return_value=SimpleNamespace(id="webhook_t")) as create:
			settings = get_settings()
			settings.save()

		self.assertTrue(settings.webhooks_secret)
		self.assertEqual(settings.webhook_id_test, "webhook_t")
		kwargs = create.call_args.kwargs
		self.assertEqual(kwargs["secret"], settings.webhooks_secret)
		self.assertEqual(kwargs["url"], settings.webhook_url)
		self.assertIn("letter.updated", kwargs["enabled_events"])

		# Saving again keeps the secret and makes no second webhook
		with patch.object(postgrid.Webhook, "create") as create_again:
			settings.save()
		create_again.assert_not_called()

	def test_reset_webhooks(self):
		set_settings(webhooks_secret=SECRET)
		ids = iter(["webhook_test", "webhook_live"])
		keys = []

		def create(**kwargs):
			keys.append(postgrid.pm_key)
			return SimpleNamespace(id=next(ids))

		doc = json.dumps({"doctype": "PostGrid Settings"})
		with patch.object(postgrid.Webhook, "create", side_effect=create):
			self.assertEqual(reset_webhooks(doc), doc)
		self.assertEqual(keys, ["test_sk_key", "live_sk_key"])

	def test_reset_webhooks_needs_write_permission(self):
		set_settings(webhooks_secret=SECRET)
		doc = json.dumps({"doctype": "PostGrid Settings"})
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user("Guest")
		with patch.object(postgrid.Webhook, "create") as create, self.assertRaises(frappe.PermissionError):
			reset_webhooks(doc)
		create.assert_not_called()

	def test_get_postgrid_defaults(self):
		set_settings(
			address_placement="Top of First Page", envelope_type="Flat", color=1, double_sided=0, express=1
		)
		self.assertEqual(
			api.get_postgrid_defaults(),
			{
				"address_placement": "top_first_page",
				"envelope_type": "flat",
				"misc": {"color": True, "double_sided": False, "express": True},
			},
		)
		set_settings(address_placement="Insert Blank Page", envelope_type="Standard Double Window")
		defaults = api.get_postgrid_defaults()
		self.assertEqual(defaults["address_placement"], "insert_blank_page")
		self.assertEqual(defaults["envelope_type"], "standard_double_window")


class TestWebhooks(IntegrationTestCase):
	def setUp(self):
		rollback_after_test(self)
		set_settings(webhooks_secret=SECRET, save_pdf_files=0, update_addresses=0)
		previous = getattr(frappe.local, "request", None)
		self.addCleanup(setattr, frappe.local, "request", previous)

	def post(self, payload, secret=SECRET):
		token = jwt.encode(payload, secret, algorithm="HS256")
		frappe.local.request = make_request(token.encode())
		return api.webhooks()

	def make_records(self, request_id):
		ig = frappe.get_doc(
			{
				"doctype": "Integration Request",
				"integration_request_service": "PostGrid",
				"request_id": request_id,
				"status": "Queued",
			}
		).insert(ignore_permissions=True)
		todo = frappe.get_doc({"doctype": "ToDo", "description": "Mail me"}).insert(ignore_permissions=True)
		com = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Mailed Letter",
				"communication_medium": "Other",
				"content": "Mailed",
				"delivery_status": "Scheduled",
				"message_id": request_id,
				"reference_doctype": "ToDo",
				"reference_name": todo.name,
				"sent_or_received": "Sent",
				"subject": "Mailed",
			}
		).insert(ignore_permissions=True)
		return ig.name, com.name

	def test_without_request(self):
		frappe.local.request = None
		self.assertIsNone(api.webhooks())

	def test_rejects_without_secret(self):
		set_settings(webhooks_secret=None)
		with self.assertRaises(frappe.AuthenticationError):
			self.post({"data": {"id": "letter_x", "status": "ready"}})

	def test_rejects_wrong_signature(self):
		with self.assertRaises(frappe.AuthenticationError):
			self.post({"data": {"id": "letter_x", "status": "ready"}}, secret="not-the-secret")

	def test_rejects_garbage(self):
		frappe.local.request = make_request(b"not a token")
		with self.assertRaises(frappe.AuthenticationError):
			api.webhooks()

	def test_updates_status(self):
		ig, com = self.make_records("letter_status")
		self.assertEqual(self.post({"data": {"id": "letter_status", "status": "printing"}}), 200)
		self.assertEqual(frappe.db.get_value("Integration Request", ig, "status"), "Authorized")
		self.assertEqual(frappe.db.get_value("Communication", com, "delivery_status"), "Sending")

	def test_ignores_unknown_status(self):
		# Return envelope orders have their own statuses, which aren't in STATUS_MAP
		set_settings(update_addresses=1)
		ig, com = self.make_records("return_envelope_order_x")
		address = make_address("Unchanged", postgrid_id="contact_unchanged")
		payload = {
			"data": {
				"id": "return_envelope_order_x",
				"status": "placed",
				"to": {"id": "contact_unchanged", "addressStatus": "verified", "city": "Elsewhere"},
			}
		}
		self.assertEqual(self.post(payload), 200)
		self.assertEqual(frappe.db.get_value("Integration Request", ig, "status"), "Queued")
		self.assertEqual(frappe.db.get_value("Communication", com, "delivery_status"), "Scheduled")
		self.assertEqual(frappe.db.get_value("Address", address, "city"), "Lancaster")

	def test_saves_pdf_once(self):
		set_settings(save_pdf_files=1)
		_, com = self.make_records("letter_pdf")
		session = MagicMock()
		session.get.return_value = SimpleNamespace(content=make_pdf())
		payload = {"data": {"id": "letter_pdf", "status": "completed", "url": "https://pdf.example/x.pdf"}}
		with patch("frappe.utils.get_request_session", return_value=session):
			self.post(payload)
			self.post(payload)

		session.get.assert_called_once_with("https://pdf.example/x.pdf")
		files = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Communication", "attached_to_name": com},
			fields=["file_name", "is_private"],
		)
		self.assertEqual(files, [{"file_name": "Letter-letter_pdf.pdf", "is_private": 1}])
		self.assertEqual(frappe.db.get_value("Communication", com, "delivery_status"), "Opened")

	def test_updates_verified_addresses(self):
		set_settings(update_addresses=1)
		verified = make_address("Old Name", postgrid_id="contact_verified")
		unverified = make_address("Unverified", postgrid_id="contact_unverified")
		self.post(
			{
				"data": {
					"id": "letter_unknown",
					"status": "cancelled",
					"to": {
						"id": "contact_verified",
						"addressStatus": "verified",
						"addressLine1": "2 New Road",
						"addressLine2": "Suite 5",
						"city": "Lititz",
						"provinceOrState": "PA",
						"postalOrZip": "17543",
						"companyName": "New Name",
					},
					"from": {"id": "contact_unverified", "addressStatus": "failed", "city": "Nowhere"},
				}
			}
		)
		address = frappe.get_doc("Address", verified)
		self.assertEqual(
			tuple(
				address.get(f) for f in ("address_line1", "address_line2", "city", "pincode", "address_title")
			),
			("2 New Road", "Suite 5", "Lititz", "17543", "New Name"),
		)
		self.assertEqual(frappe.db.get_value("Address", unverified, "city"), "Lancaster")

	def test_update_address_ignores_unknown(self):
		api.update_address(None)
		api.update_address({"addressStatus": "verified"})
		api.update_address({"id": "contact_nobody", "addressStatus": "verified", "city": "X"})
		self.assertFalse(frappe.db.exists("Address", {"postgrid_id": "contact_nobody"}))


class TestMailLetter(IntegrationTestCase):
	def setUp(self):
		rollback_after_test(self)
		set_settings(
			mode="Test",
			pm_key_test="test_sk_key",
			address_placement="Insert Blank Page",
			envelope_type="Flat",
			color=0,
			double_sided=1,
			express=0,
		)
		self.from_address = make_address("Avunu LLC", address_line1="100 Sender Way")
		self.to_address = make_address(
			"Customer Inc", address_line1="200 Receiver Road", address_line2="Floor 2"
		)
		self.contact = make_contact("Ada", "Lovelace")
		self.todo = frappe.get_doc({"doctype": "ToDo", "description": "Mail me"}).insert(
			ignore_permissions=True
		)
		get_print = patch("frappe.get_print", side_effect=lambda **kwargs: make_pdf())
		self.get_print = get_print.start()
		self.addCleanup(get_print.stop)

	def mail(self, **kwargs):
		return api.mail_letter(
			doctype="ToDo",
			docname=self.todo.name,
			print_format="Standard",
			from_address=self.from_address,
			to_address=self.to_address,
			**kwargs,
		)

	def test_mails_with_settings_defaults(self):
		with patch.object(postgrid.Letter, "create", return_value=make_letter("letter_defaults")) as create:
			result = self.mail()

		self.assertEqual(result["indicator"], "green")
		self.assertEqual(postgrid.pm_key, "test_sk_key")
		request = create.call_args.kwargs
		self.assertEqual(request["address_placement"], "insert_blank_page")
		self.assertEqual(request["envelope_type"], "flat")
		self.assertEqual(
			(request["color"], request["double_sided"], request["express"]), (False, True, False)
		)
		self.assertEqual(request["from_"]["company_name"], "Avunu LLC")
		self.assertEqual(request["from_"]["country_code"], "us")
		self.assertEqual(request["to"]["address_line2"], "Floor 2")
		self.assertIsNone(request["to"]["first_name"])
		self.assertEqual(request["pdf"].name, f"ToDo-{self.todo.name}.pdf")
		self.assertEqual(count_pages(request["pdf"]), 1)

		# PostGrid's contact ids land on the addresses
		self.assertEqual(frappe.db.get_value("Address", self.from_address, "postgrid_id"), "contact_from")
		self.assertEqual(frappe.db.get_value("Address", self.to_address, "postgrid_id"), "contact_to")

		ig = frappe.get_last_doc("Integration Request", filters={"request_id": "letter_defaults"})
		self.assertEqual(
			(ig.status, ig.reference_doctype, ig.reference_docname), ("Queued", "ToDo", self.todo.name)
		)
		self.assertIn(ig.name, result["message"])

		communication = frappe.get_last_doc("Communication", filters={"message_id": "letter_defaults"})
		self.assertEqual(communication.communication_type, "Mailed Letter")
		self.assertEqual(communication.delivery_status, "Scheduled")
		self.assertEqual(communication.reference_name, self.todo.name)
		self.assertIn("200 Receiver Road", communication.content)

		timeline = api.get_timeline_content("ToDo", self.todo.name)
		self.assertEqual(len(timeline), 1)
		self.assertEqual(timeline[0]["template"], "direct_mail_timeline")
		self.assertEqual(timeline[0]["template_data"]["message_id"], "letter_defaults")
		self.assertIsNone(timeline[0]["template_data"]["file_url"])

	def test_mails_with_dialog_values_and_cover_letter(self):
		# The print view sends its dialog's values as JSON, with the ticked options as a list
		pg_parameters = json.dumps(
			{
				"address_placement": "top_first_page",
				"envelope_type": "standard_double_window",
				"misc": ["double_sided", "color"],
				"to_contact": self.contact,
			}
		)
		with patch.object(postgrid.Letter, "create", return_value=make_letter("letter_cover")) as create:
			result = self.mail(pg_parameters=pg_parameters, cl_print_format="Standard")

		self.assertEqual(result["indicator"], "green")
		request = create.call_args.kwargs
		self.assertEqual(request["address_placement"], "top_first_page")
		self.assertEqual((request["double_sided"], request["color"]), (True, True))
		self.assertNotIn("express", request)
		self.assertEqual((request["to"]["first_name"], request["to"]["last_name"]), ("Ada", "Lovelace"))
		# cover letter, the blank back of a double-sided cover, then the document
		self.assertEqual(count_pages(request["pdf"]), 3)
		self.assertEqual(self.get_print.call_count, 2)

	def test_mails_to_the_contact_argument(self):
		# A Mailed Letter notification passes its To Contact Field's value as to_contact, outside pg_parameters
		with patch.object(postgrid.Letter, "create", return_value=make_letter("letter_contact")) as create:
			self.mail(to_contact=self.contact, pg_parameters={"misc": {}})
		to = create.call_args.kwargs["to"]
		self.assertEqual((to["first_name"], to["last_name"]), ("Ada", "Lovelace"))

	def test_failure_is_recorded(self):
		error = postgrid.PMError(
			status_code=400, object="error", type="validation_error", message="Bad address"
		)
		with patch.object(postgrid.Letter, "create", side_effect=error):
			result = self.mail(pg_parameters={"misc": {}})

		self.assertEqual(result["indicator"], "red")
		ig = frappe.get_last_doc("Integration Request", filters={"request_id": "error"})
		self.assertEqual(ig.status, "Failed")
		self.assertEqual(ig.error, "Bad address")
		self.assertIn(ig.name, result["message"])
		self.assertFalse(frappe.db.exists("Communication", {"reference_name": self.todo.name}))

	def test_timeline_links_the_saved_pdf(self):
		with patch.object(postgrid.Letter, "create", return_value=make_letter("letter_file")):
			self.mail()
		communication = frappe.get_last_doc("Communication", filters={"message_id": "letter_file"})
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "Letter-letter_file.pdf",
				"attached_to_doctype": "Communication",
				"attached_to_name": communication.name,
				"content": make_pdf(),
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		timeline = api.get_timeline_content("ToDo", self.todo.name)
		self.assertEqual(timeline[0]["template_data"]["file_url"], file.get("file_url"))
