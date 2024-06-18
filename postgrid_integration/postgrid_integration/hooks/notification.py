# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

import frappe
from frappe.email.doctype.notification.notification import (
    Notification,
    evaluate_alert,
    get_context,
)
from postgrid_integration.postgrid_integration.doctype.postgrid_settings import (
    mail_letter,
)
from postgrid_integration.config import MAIL_TYPES


class MailedNotification(Notification):

    def __init__(self, *args, **kwargs):
        super(MailedNotification, self).__init__(*args, **kwargs)
        self.pg_parameters = {
            "address_placement": self.address_placement,
            "envelope_type": self.envelope_type,
            "with_cover_letter": self.with_cover_letter,
            "misc": {
                "color": self.color,
                "double_sided": self.double_sided,
                "express": self.express,
            },
        }

    def send(self, doc):
        context = get_context(doc)
        if self.channel == "Mailed Letter":
            from_address = self.from_address
            to_address = doc.get(self.to_address_document_field)
            to_contact = doc.get(self.to_contact_document_field, None)
            if not to_address:
                frappe.log_error(
                    title="Failed to mail notification",
                    message=f"Could not find address for {doc.name}",
                )
                return
            try:

                if self.with_cover_letter:
                    mail_letter(
                        doctype=doc.doctype,
                        docname=doc.name,
                        print_format=self.print_format,
                        from_address=from_address,
                        to_address=to_address,
                        to_contact=to_contact,
                        pg_parameters=self.pg_parameters,
                        cl_print_format=self.cl_print_format,
                    )
                else:
                    mail_letter(
                        doc.doctype, doc.name, self.print_format, self.pg_parameters
                    )
            except:
                frappe.log_error(
                    title="Failed to mail notification", message=frappe.get_traceback()
                )


def trigger_daily_mailed_letter_notifications():
    if frappe.flags.in_import or frappe.flags.in_patch:
        # don"t send notifications while syncing or patching
        return

    notification_list = frappe.get_all(
        "Notification",
        filters={
            "event": ["in", ["Days Before", "Days After"]],
            "channel": ["in", MAIL_TYPES],
            "enabled": 1,
        },
        pluck="name",
    )
    for n in notification_list:
        notification = MailedNotification(n)

        for doc in notification.get_documents_for_today():
            evaluate_alert(doc, notification, notification.event)
            frappe.db.commit()


def run_mailed_notifications(doc, method):
    """Run notifications for any relavant doc methods"""
    if (
        (frappe.flags.in_import and frappe.flags.mute_emails)
        or frappe.flags.in_patch
        or frappe.flags.in_install
    ):
        return

    if doc.flags.mailed_notifications_executed is None:
        doc.flags.mailed_notifications_executed = []

    if doc.flags.mailed_notifications is None:

        def _get_notifications():
            """returns enabled notifications for the current doctype"""

            return frappe.get_all(
                "Notification",
                fields=["name", "event", "method"],
                filters={
                    "enabled": 1,
                    "document_type": doc.doctype,
                    "channel": ["in", MAIL_TYPES],
                },
            )

        doc.flags.mailed_notifications = frappe.cache.hget(
            "notifications", doc.doctype, _get_notifications
        )

    if not doc.flags.mailed_notifications:
        return

    def _evaluate_alert(notification):
        if notification.name in doc.flags.mailed_notifications_executed:
            return

        notification = MailedNotification(notification.name)

        evaluate_alert(doc, notification.name, notification.event)

        doc.flags.mailed_notifications_executed.append(notification.name)

    event_map = {
        "on_update": "Save",
        "after_insert": "New",
        "on_submit": "Submit",
        "on_cancel": "Cancel",
    }

    if not doc.flags.in_insert:
        # value change is not applicable in insert
        event_map["on_change"] = "Value Change"

    for notification in doc.flags.mailed_notifications:
        event = event_map.get(method, None)
        if event and notification.event == event:
            _evaluate_alert(notification)
        elif notification.event == "Method" and method == notification.method:
            _evaluate_alert(notification)
