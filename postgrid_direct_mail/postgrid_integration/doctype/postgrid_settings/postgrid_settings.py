# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

from types import ModuleType
from typing import TYPE_CHECKING, Any

import frappe
import postgrid
from frappe import _
from frappe.model.document import Document

if TYPE_CHECKING:
	from frappe.types import DF


class PostGridSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	if TYPE_CHECKING:
		address_placement: DF.Literal["Insert Blank Page", "Top of First Page"]
		color: DF.Check
		double_sided: DF.Check
		envelope_type: DF.Literal["Standard Double Window", "Flat"]
		express: DF.Check
		mode: DF.Literal["Test", "Live"]
		pm_key_live: DF.Password | None
		pm_key_test: DF.Password | None
		save_pdf_files: DF.Check
		update_addresses: DF.Check
		webhook_id_live: DF.ReadOnly | None
		webhook_id_test: DF.ReadOnly | None
		webhooks_secret: DF.ReadOnly | None
	# end: auto-generated types

	client: ModuleType
	webhook_url: str

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.webhook_url = frappe.utils.get_url(
			"/api/method/postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.webhooks"
		)

	def initialize_client(self) -> ModuleType:
		"""Point the PostGrid client at the current mode's API key, and return it.

		Called when the client is needed, not on load: loading the settings (the print view does, for
		its defaults) then needs no key, and installing the app on a new site, where no mode is set yet,
		works.
		"""
		postgrid.pm_key = self.get_password(f"pm_key_{self.mode.lower()}")
		self.client = postgrid
		return postgrid

	def validate(self):
		if not self.get("mode"):
			# frappe's mandatory check, which runs after validate, reports it
			return
		self.initialize_client()
		if not self.webhooks_secret:
			self.generate_webhooks_secret()
		if not self.get(f"webhook_id_{self.mode.lower()}"):
			self.create_webhook()

	def generate_webhooks_secret(self):
		self.webhooks_secret = frappe.generate_hash()

	def create_webhook(self):
		webhook = self.client.Webhook.create(
			enabled_events=[
				"cheque.created",
				"cheque.updated",
				"letter.created",
				"letter.updated",
				"postcard.created",
				"postcard.updated",
				"return_envelope_order.created",
				"return_envelope_order.updated",
			],
			url=self.webhook_url,
			description="Direct Mail via PostGrid Webhook",
			secret=self.webhooks_secret,
		)
		self.set(f"webhook_id_{self.mode.lower()}", webhook.id)

	def delete_webhook(self):
		"""Delete the current mode's registered webhook from PostGrid, if there is one."""
		webhook_id = self.get(f"webhook_id_{self.mode.lower()}")
		if not webhook_id:
			return
		try:
			self.client.Webhook.delete(webhook_id)
		except postgrid.PMError as e:
			# Already gone, for example deleted in PostGrid's dashboard
			if e.status_code != 404:
				raise


def describe_error(error: Exception) -> str:
	"""A short reason for a failed PostGrid call, escaped for the Reset Webhooks report's HTML."""
	return frappe.utils.escape_html(str(getattr(error, "message", None) or error) or type(error).__name__)


@frappe.whitelist()
def reset_webhooks(doc: str | dict[str, Any]) -> dict[str, Any]:
	"""Replace the webhook on the Test and the Live account (the settings form's Reset Webhooks action).

	A mode without an API key is skipped: nothing is deleted or created on its account and its webhook
	id is left as it is. With neither key set, nothing happens and the user is told to add one.

	Each mode is reset on its own, and its outcome is committed as soon as it is known, so a failure in
	one mode (an invalid key, a PostGrid error) never undoes what the other mode did at PostGrid. A
	stored id always matches PostGrid: it is the new webhook's id when the reset worked, the old id when
	the old webhook could not be deleted, and empty when the old one was deleted but no new one could
	be registered. The report names each mode reset, skipped or failed, with the reason. When a mode
	failed and no stored id changed, it raises; otherwise it shows the report as an error and returns
	the settings, so the form shows the ids that are stored.
	"""
	pgs = frappe.get_single("PostGrid Settings")
	# Whitelisted: only users who may edit the settings may register webhooks with their API keys
	pgs.check_permission("write")
	# Decide which modes to reset before touching PostGrid, so a missing key never leaves a mode
	# half-reset (its old webhook deleted and no new one made)
	modes = [m for m in ("Test", "Live") if pgs.get_password(f"pm_key_{m.lower()}", raise_exception=False)]
	if not modes:
		frappe.throw(
			_("Reset Webhooks needs an API key. Enter the Test or the Live API key, save, and try again."),
			title=_("No API Key"),
		)
	mode = pgs.mode
	reset: list[str] = []
	failures: list[str] = []
	changed = False
	for webhook_mode in modes:
		pgs.mode = webhook_mode
		fieldname = f"webhook_id_{webhook_mode.lower()}"
		try:
			pgs.initialize_client()
			# Delete the old webhook first, or PostGrid would send every event to both
			pgs.delete_webhook()
		except Exception as e:
			# Nothing changed at PostGrid for this mode, so its stored id stays as it is
			failures.append(
				_("Could not reset the {0} webhook: {1}. Its webhook was not changed.").format(
					_(webhook_mode), describe_error(e)
				)
			)
			continue
		try:
			pgs.create_webhook()
		except Exception as e:
			if not pgs.get(fieldname):
				# There was no old webhook, so nothing changed at PostGrid or in the settings
				failures.append(
					_("Could not register a {0} webhook: {1}. Its webhook was not changed.").format(
						_(webhook_mode), describe_error(e)
					)
				)
				continue
			# The old webhook is gone at PostGrid, so stop recording its id
			pgs.set(fieldname, None)
			failures.append(
				_(
					"Could not register a new {0} webhook: {1}. The old one was deleted, so {0} has no webhook"
					" until Reset Webhooks succeeds or the settings are saved in {0} mode."
				).format(_(webhook_mode), describe_error(e))
			)
		else:
			reset.append(webhook_mode)
		pgs.db_set(fieldname, pgs.get(fieldname))
		# Keep this mode's outcome even if a later mode fails and the request is rolled back
		frappe.db.commit()
		changed = True
	pgs.mode = mode

	messages = []
	if len(reset) == 2:
		messages.append(_("Reset the Test and Live webhooks."))
	elif reset:
		messages.append(_("Reset the {0} webhook.").format(_(reset[0])))
	messages.extend(failures)
	messages.extend(
		_("Skipped {0}: it has no API key.").format(_(m)) for m in ("Test", "Live") if m not in modes
	)
	message = "<br>".join(messages)
	if failures and not changed:
		frappe.throw(message, title=_("Webhooks Not Reset"))
	if failures:
		frappe.msgprint(message, title=_("Webhooks Not Reset"), indicator="red")
	else:
		frappe.msgprint(message, title=_("Webhooks Reset"), indicator="green")
	# The form applies the returned settings, so it shows the stored webhook ids
	return pgs.as_dict()
