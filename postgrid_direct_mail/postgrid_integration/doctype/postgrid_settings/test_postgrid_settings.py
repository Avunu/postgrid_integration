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
	describe_error,
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
		# Reset Webhooks commits after each mode; a real commit would end the test's savepoint
		commit = patch.object(frappe.db, "commit")
		self.commit = commit.start()
		self.addCleanup(commit.stop)

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
		set_settings(webhooks_secret=SECRET, mode="Live", webhook_id_test="webhook_old_test")
		ids = iter(["webhook_test", "webhook_live"])
		calls = []

		def create(**kwargs):
			calls.append(("create", postgrid.pm_key))
			return SimpleNamespace(id=next(ids))

		def delete(webhook_id):
			calls.append(("delete", postgrid.pm_key, webhook_id))

		doc = json.dumps({"doctype": "PostGrid Settings"})
		with (
			patch.object(postgrid.Webhook, "create", side_effect=create),
			patch.object(postgrid.Webhook, "delete", side_effect=delete),
		):
			result = reset_webhooks(doc)

		# The old Test webhook is deleted before its replacement is made; Live had none to delete
		self.assertEqual(
			calls,
			[
				("delete", "test_sk_key", "webhook_old_test"),
				("create", "test_sk_key"),
				("create", "live_sk_key"),
			],
		)
		# The new ids are stored, the mode is left alone, and the form gets them back
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_test", "webhook_live")
		)
		self.assertEqual(settings.mode, "Live")
		self.assertEqual(
			(result["webhook_id_test"], result["webhook_id_live"]), ("webhook_test", "webhook_live")
		)
		self.assertEqual(result["mode"], "Live")

	def test_reset_webhooks_when_the_old_one_is_gone(self):
		set_settings(webhooks_secret=SECRET, webhook_id_test="webhook_gone", webhook_id_live="webhook_gone")
		not_found = postgrid.PMError(status_code=404, object="error", type="not_found", message="Not found")
		ids = iter(["webhook_test", "webhook_live"])
		with (
			patch.object(
				postgrid.Webhook, "create", side_effect=lambda **kwargs: SimpleNamespace(id=next(ids))
			),
			patch.object(postgrid.Webhook, "delete", side_effect=not_found),
		):
			reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_test", "webhook_live")
		)

	def test_reset_webhooks_stops_when_delete_fails(self):
		# With every mode failing before anything changed, it raises and keeps the stored ids
		set_settings(
			webhooks_secret=SECRET, webhook_id_test="webhook_old_test", webhook_id_live="webhook_old_live"
		)
		error = postgrid.PMError(status_code=401, object="error", type="unauthorized", message="Bad key")
		with (
			patch.object(postgrid.Webhook, "create") as create,
			patch.object(postgrid.Webhook, "delete", side_effect=error),
			self.assertRaisesRegex(frappe.ValidationError, "Could not reset the Test webhook: Bad key"),
		):
			reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))
		create.assert_not_called()
		self.commit.assert_not_called()
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_old_test", "webhook_old_live")
		)

	def record_calls(self, create_results: dict, delete_errors: dict | None = None) -> list:
		"""Patch PostGrid's webhook calls and frappe's commit, and record them in order.

		`create_results` maps an API key to the id `Webhook.create` returns, or to the error it raises;
		`delete_errors` maps an API key to the error `Webhook.delete` raises.
		"""
		calls: list = []
		delete_errors = delete_errors or {}

		def create(**kwargs):
			calls.append(("create", postgrid.pm_key))
			result = create_results[postgrid.pm_key]
			if isinstance(result, Exception):
				raise result
			return SimpleNamespace(id=result)

		def delete(webhook_id):
			calls.append(("delete", postgrid.pm_key, webhook_id))
			if postgrid.pm_key in delete_errors:
				raise delete_errors[postgrid.pm_key]

		self.commit.side_effect = lambda: calls.append(("commit",))
		for name, side_effect in (("create", create), ("delete", delete)):
			patcher = patch.object(postgrid.Webhook, name, side_effect=side_effect)
			patcher.start()
			self.addCleanup(patcher.stop)
		return calls

	def last_indicator(self) -> str | None:
		return frappe.local.message_log[-1].get("indicator") if frappe.local.message_log else None

	def test_reset_webhooks_keeps_test_when_live_delete_fails(self):
		# Test is replaced and committed before Live fails on an invalid key, so the new Test id is kept
		set_settings(
			webhooks_secret=SECRET, webhook_id_test="webhook_old_test", webhook_id_live="webhook_old_live"
		)
		bad_key = postgrid.PMError(
			status_code=401, object="error", type="unauthorized", message="Invalid API key"
		)
		calls = self.record_calls({"test_sk_key": "webhook_test"}, {"live_sk_key": bad_key})
		frappe.local.message_log = []
		result = reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))

		self.assertEqual(
			calls,
			[
				("delete", "test_sk_key", "webhook_old_test"),
				("create", "test_sk_key"),
				("commit",),
				("delete", "live_sk_key", "webhook_old_live"),
			],
		)
		# Live's old webhook is still at PostGrid, so its id stays
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_test", "webhook_old_live")
		)
		self.assertEqual(
			(result["webhook_id_test"], result["webhook_id_live"]), ("webhook_test", "webhook_old_live")
		)
		self.assertEqual(settings.mode, "Test")
		message = self.last_message()
		self.assertIn("Reset the Test webhook.", message)
		self.assertIn(
			"Could not reset the Live webhook: Invalid API key. Its webhook was not changed.", message
		)
		self.assertEqual(self.last_indicator(), "red")

	def test_reset_webhooks_keeps_test_when_live_create_fails(self):
		# Live's old webhook is deleted and PostGrid then fails to make the new one: Live's id is cleared,
		# since it names a webhook that no longer exists, and Test's new id is kept
		set_settings(
			webhooks_secret=SECRET, webhook_id_test="webhook_old_test", webhook_id_live="webhook_old_live"
		)
		server_error = postgrid.PMError(
			status_code=500, object="error", type="api_error", message="PostGrid is down"
		)
		calls = self.record_calls({"test_sk_key": "webhook_test", "live_sk_key": server_error})
		frappe.local.message_log = []
		result = reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))

		self.assertEqual(
			calls,
			[
				("delete", "test_sk_key", "webhook_old_test"),
				("create", "test_sk_key"),
				("commit",),
				("delete", "live_sk_key", "webhook_old_live"),
				("create", "live_sk_key"),
				("commit",),
			],
		)
		settings = get_settings()
		self.assertEqual(settings.webhook_id_test, "webhook_test")
		self.assertFalse(settings.webhook_id_live)
		self.assertEqual(result["webhook_id_test"], "webhook_test")
		self.assertFalse(result["webhook_id_live"])
		message = self.last_message()
		self.assertIn("Reset the Test webhook.", message)
		self.assertIn("Could not register a new Live webhook: PostGrid is down.", message)
		self.assertEqual(self.last_indicator(), "red")

	def test_reset_webhooks_resets_live_when_test_fails(self):
		# A failure in Test does not stop Live, and Test's id stays as PostGrid has it
		set_settings(
			webhooks_secret=SECRET, webhook_id_test="webhook_old_test", webhook_id_live="webhook_old_live"
		)
		bad_key = postgrid.PMError(
			status_code=401, object="error", type="unauthorized", message="Invalid API key"
		)
		calls = self.record_calls({"live_sk_key": "webhook_live"}, {"test_sk_key": bad_key})
		frappe.local.message_log = []
		result = reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))

		self.assertEqual(
			calls,
			[
				("delete", "test_sk_key", "webhook_old_test"),
				("delete", "live_sk_key", "webhook_old_live"),
				("create", "live_sk_key"),
				("commit",),
			],
		)
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_old_test", "webhook_live")
		)
		self.assertEqual(result["webhook_id_live"], "webhook_live")
		message = self.last_message()
		self.assertIn("Reset the Live webhook.", message)
		self.assertIn("Could not reset the Test webhook: Invalid API key.", message)
		self.assertEqual(self.last_indicator(), "red")

	def test_reset_webhooks_clears_test_when_test_create_fails(self):
		# Test's old webhook is deleted but no new one is made; a non-PostGrid error (a dropped connection)
		# is reported the same way, and Live is still reset
		set_settings(webhooks_secret=SECRET, webhook_id_test="webhook_old_test")
		calls = self.record_calls(
			{"test_sk_key": ConnectionError("Connection reset"), "live_sk_key": "webhook_live"}
		)
		frappe.local.message_log = []
		reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))

		self.assertEqual(
			calls,
			[
				("delete", "test_sk_key", "webhook_old_test"),
				("create", "test_sk_key"),
				("commit",),
				("create", "live_sk_key"),
				("commit",),
			],
		)
		settings = get_settings()
		self.assertFalse(settings.webhook_id_test)
		self.assertEqual(settings.webhook_id_live, "webhook_live")
		message = self.last_message()
		self.assertIn("Reset the Live webhook.", message)
		self.assertIn("Could not register a new Test webhook: Connection reset.", message)

	def test_reset_webhooks_without_an_old_id_when_create_fails(self):
		# With no stored id nothing is deleted, so a failed create changes nothing: it must not claim an
		# old webhook was deleted, must not commit, and with every mode failing it raises
		set_settings(webhooks_secret=SECRET)
		bad_key = postgrid.PMError(
			status_code=401, object="error", type="unauthorized", message="Invalid API key"
		)
		calls = self.record_calls({"test_sk_key": bad_key, "live_sk_key": bad_key})
		with self.assertRaises(frappe.ValidationError) as raised:
			reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))

		self.assertEqual(calls, [("create", "test_sk_key"), ("create", "live_sk_key")])
		message = str(raised.exception)
		self.assertIn(
			"Could not register a Test webhook: Invalid API key. Its webhook was not changed.", message
		)
		self.assertIn(
			"Could not register a Live webhook: Invalid API key. Its webhook was not changed.", message
		)
		self.assertNotIn("deleted", message)
		settings = get_settings()
		self.assertFalse(settings.webhook_id_test)
		self.assertFalse(settings.webhook_id_live)

	def test_reset_webhooks_commits_each_mode(self):
		# Both succeed: each mode's new id is committed as soon as it is made
		set_settings(
			webhooks_secret=SECRET, webhook_id_test="webhook_old_test", webhook_id_live="webhook_old_live"
		)
		calls = self.record_calls({"test_sk_key": "webhook_test", "live_sk_key": "webhook_live"})
		frappe.local.message_log = []
		reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))

		self.assertEqual(
			calls,
			[
				("delete", "test_sk_key", "webhook_old_test"),
				("create", "test_sk_key"),
				("commit",),
				("delete", "live_sk_key", "webhook_old_live"),
				("create", "live_sk_key"),
				("commit",),
			],
		)
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_test", "webhook_live")
		)
		self.assertEqual(self.last_message(), "Reset the Test and Live webhooks.")
		self.assertEqual(self.last_indicator(), "green")

	def test_describe_error(self):
		error = postgrid.PMError(status_code=401, object="error", type="unauthorized", message="Bad key")
		self.assertEqual(describe_error(error), "Bad key")
		self.assertEqual(describe_error(TimeoutError("timed out")), "timed out")
		self.assertEqual(describe_error(TimeoutError()), "TimeoutError")
		self.assertEqual(describe_error(ValueError("<b>bad</b>")), "&lt;b&gt;bad&lt;/b&gt;")

	def remove_key(self, mode: str):
		from frappe.utils.password import remove_encrypted_password

		remove_encrypted_password("PostGrid Settings", "PostGrid Settings", f"pm_key_{mode}")
		frappe.db.set_single_value("PostGrid Settings", f"pm_key_{mode}", None)

	def last_message(self) -> str:
		return frappe.local.message_log[-1]["message"] if frappe.local.message_log else ""

	def test_reset_webhooks_skips_a_mode_without_a_key(self):
		# With only a Test key, Test is reset and nothing is deleted or created for Live
		self.remove_key("live")
		set_settings(
			webhooks_secret=SECRET, webhook_id_test="webhook_old_test", webhook_id_live="webhook_old_live"
		)
		calls = []

		def create(**kwargs):
			calls.append(("create", postgrid.pm_key))
			return SimpleNamespace(id="webhook_test")

		def delete(webhook_id):
			calls.append(("delete", postgrid.pm_key, webhook_id))

		frappe.local.message_log = []
		with (
			patch.object(postgrid.Webhook, "create", side_effect=create),
			patch.object(postgrid.Webhook, "delete", side_effect=delete),
		):
			result = reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))

		self.assertEqual(calls, [("delete", "test_sk_key", "webhook_old_test"), ("create", "test_sk_key")])
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_test", "webhook_old_live")
		)
		self.assertEqual(result["webhook_id_live"], "webhook_old_live")
		self.assertEqual(settings.mode, "Test")
		message = self.last_message()
		self.assertIn("Reset the Test webhook.", message)
		self.assertIn("Skipped Live: it has no API key.", message)

	def test_reset_webhooks_with_only_a_live_key(self):
		self.remove_key("test")
		set_settings(webhooks_secret=SECRET, webhook_id_test="webhook_old_test")
		frappe.local.message_log = []
		with (
			patch.object(
				postgrid.Webhook, "create", return_value=SimpleNamespace(id="webhook_live")
			) as create,
			patch.object(postgrid.Webhook, "delete") as delete,
		):
			reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))
		delete.assert_not_called()
		create.assert_called_once()
		settings = get_settings()
		self.assertEqual(
			(settings.webhook_id_test, settings.webhook_id_live), ("webhook_old_test", "webhook_live")
		)
		message = self.last_message()
		self.assertIn("Reset the Live webhook.", message)
		self.assertIn("Skipped Test: it has no API key.", message)

	def test_reset_webhooks_reports_both_modes(self):
		set_settings(webhooks_secret=SECRET)
		ids = iter(["webhook_test", "webhook_live"])
		frappe.local.message_log = []
		with patch.object(
			postgrid.Webhook, "create", side_effect=lambda **kwargs: SimpleNamespace(id=next(ids))
		):
			reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))
		message = self.last_message()
		self.assertIn("Reset the Test and Live webhooks.", message)
		self.assertNotIn("Skipped", message)

	def test_reset_webhooks_needs_a_key(self):
		# With neither key, nothing is deleted or created and the user is told why
		self.remove_key("test")
		self.remove_key("live")
		set_settings(webhooks_secret=SECRET, webhook_id_test="webhook_old_test")
		with (
			patch.object(postgrid.Webhook, "create") as create,
			patch.object(postgrid.Webhook, "delete") as delete,
			self.assertRaisesRegex(frappe.ValidationError, "needs an API key"),
		):
			reset_webhooks(json.dumps({"doctype": "PostGrid Settings"}))
		delete.assert_not_called()
		create.assert_not_called()
		self.assertEqual(get_settings().webhook_id_test, "webhook_old_test")

	def test_reset_webhooks_needs_write_permission(self):
		set_settings(webhooks_secret=SECRET)
		doc = json.dumps({"doctype": "PostGrid Settings"})
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user("Guest")
		with (
			patch.object(postgrid.Webhook, "create") as create,
			patch.object(postgrid.Webhook, "delete") as delete,
			self.assertRaises(frappe.PermissionError),
		):
			reset_webhooks(doc)
		create.assert_not_called()
		delete.assert_not_called()

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
