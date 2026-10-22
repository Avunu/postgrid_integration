# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

from types import ModuleType
from typing import TYPE_CHECKING, Any

import frappe
import postgrid
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


@frappe.whitelist()
def reset_webhooks(doc: str | dict[str, Any]) -> dict[str, Any]:
	"""Replace the webhook on the Test and the Live account (the settings form's Reset Webhooks action)."""
	pgs = frappe.get_single("PostGrid Settings")
	# Whitelisted: only users who may edit the settings may register webhooks with their API keys
	pgs.check_permission("write")
	mode = pgs.mode
	for webhook_mode in ["Test", "Live"]:
		pgs.mode = webhook_mode
		pgs.initialize_client()
		# Delete the old webhook first, or PostGrid would send every event to both
		pgs.delete_webhook()
		pgs.create_webhook()
		fieldname = f"webhook_id_{webhook_mode.lower()}"
		pgs.db_set(fieldname, pgs.get(fieldname))
	pgs.mode = mode
	# The form applies the returned settings, so it shows the new webhook ids
	return pgs.as_dict()
