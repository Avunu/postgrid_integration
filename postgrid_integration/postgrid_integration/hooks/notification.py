# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

"""Mailed Letter notifications, as an extension of frappe's Notification controller.

frappe runs every enabled notification itself: on the document events (`Document.run_notifications`)
and daily for the Days Before and Days After ones. It sends each one through
`send_notification_by_channel`, so this extension mails the document there and leaves the other
channels to frappe.
"""

from typing import TYPE_CHECKING, Any

import frappe
from frappe.email.doctype.notification.notification import Notification

from postgrid_integration.postgrid_integration.doctype.postgrid_settings import mail_letter

if TYPE_CHECKING:
	from frappe.model.document import Document
	from frappe.types import DF

# The events a Mailed Letter notification mails on. Until it moved onto frappe's own notification
# run, the app hooked only after_insert, on_update, on_submit and on_cancel, and the daily job, so
# Value Change and the Minutes Before and After events never mailed. They still don't: turning them on
# would start mailing (and paying for) letters on sites with such notifications set up.
MAILED_EVENTS = frozenset({"New", "Save", "Submit", "Cancel", "Days Before", "Days After"})
MAILED_METHODS = frozenset({"after_insert", "on_update", "on_submit", "on_cancel"})


class DirectMailNotification(Notification):
	if TYPE_CHECKING:
		# Custom fields (custom/notification.json)
		address_placement: DF.Literal["Insert Blank Page", "Top of First Page"]
		cl_print_format: DF.Link | None
		color: DF.Check
		double_sided: DF.Check
		envelope_type: DF.Literal["Standard Double Window", "Flat"]
		express: DF.Check
		from_address: DF.Link | None
		to_address_document_field: str | None
		to_contact_document_field: str | None
		with_cover_letter: DF.Check

	def send_notification_by_channel(self, doc: Document, context: dict[str, Any]) -> None:
		if self.channel == "Mailed Letter" and self.mails_on_event():
			self.mail_document(doc)
		# frappe sends nothing on a channel it doesn't know, but still sends the system notification
		super().send_notification_by_channel(doc, context)

	def mails_on_event(self) -> bool:
		return self.event in MAILED_EVENTS or (self.event == "Method" and self.method in MAILED_METHODS)

	def get_pg_parameters(self) -> dict[str, Any]:
		return {
			"address_placement": (
				"top_first_page" if self.address_placement == "Top of First Page" else "insert_blank_page"
			),
			"envelope_type": (
				"standard_double_window" if self.envelope_type == "Standard Double Window" else "flat"
			),
			"misc": {
				"color": self.color,
				"double_sided": self.double_sided,
				"express": self.express,
			},
		}

	def mail_document(self, doc: Document) -> None:
		to_address = doc.get(self.to_address_document_field) if self.to_address_document_field else None
		to_contact = doc.get(self.to_contact_document_field) if self.to_contact_document_field else None
		if not to_address or not self.from_address:
			frappe.log_error(
				title="Failed to mail notification",
				message=f"Could not find address for {doc.name}",
			)
			return
		try:
			mail_letter(
				doctype=doc.doctype,
				docname=doc.name,
				print_format=self.print_format,
				from_address=self.from_address,
				to_address=to_address,
				to_contact=to_contact,
				pg_parameters=self.get_pg_parameters(),
				cl_print_format=(self.cl_print_format if self.with_cover_letter else None),
			)
		except Exception:
			frappe.log_error(title="Failed to mail notification", message=frappe.get_traceback())
