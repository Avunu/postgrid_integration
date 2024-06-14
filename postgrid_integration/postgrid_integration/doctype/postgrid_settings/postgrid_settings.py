# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

import frappe
import postgrid
from frappe.model.document import Document


class PostGridSettings(Document):

    def __init__(self, *args, **kwargs):
        super(PostGridSettings, self).__init__(*args, **kwargs)
        self.webhook_url = frappe.utils.get_url(
            "/api/method/postgrid_integration.postgrid_integration.doctype.postgrid_settings.webhooks"
        )
        self.initialize_client()
        
    def initialize_client(self):
        pm_key = self.get_password(f"pm_key_{self.mode.lower()}")
        if self.get("client"):
            self.client.pm_key = pm_key
        else:
            postgrid.pm_key = pm_key
            self.client = postgrid

    def validate(self):
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
            description="PostGrid Integration Webhook",
            secret=self.webhooks_secret,
        )
        self.set(f"webhook_id_{self.mode.lower()}", webhook.id)


@frappe.whitelist()
def reset_webhooks(doc):
    pgs = frappe.get_single("PostGrid Settings")
    for mode in ["Test", "Live"]:
        pgs.mode = mode
        pgs.initialize_client()
        pgs.create_webhook()
    return doc