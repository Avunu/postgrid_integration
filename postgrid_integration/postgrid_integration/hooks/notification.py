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


class DirectMailNotification(Notification):

    def __init__(self, *args, **kwargs):
        super(DirectMailNotification, self).__init__(*args, **kwargs)
        self.pg_parameters = {
            "address_placement": (
                "top_first_page"
                if self.address_placement == "Top of First Page"
                else "insert_blank_page"
            ),
            "envelope_type": (
                "standard_double_window"
                if self.envelope_type == "Standard Double Window"
                else "flat"
            ),
            "misc": {
                "color": self.color,
                "double_sided": self.double_sided,
                "express": self.express,
            },
        }

    def send(self, doc):
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
                mail_letter(
                    doctype=doc.doctype,
                    docname=doc.name,
                    print_format=self.print_format,
                    from_address=from_address,
                    to_address=to_address,
                    to_contact=to_contact,
                    pg_parameters=self.pg_parameters,
                    cl_print_format=(
                        self.cl_print_format if self.with_cover_letter else None
                    ),
                )
            except:
                frappe.log_error(
                    title="Failed to mail notification", message=frappe.get_traceback()
                )


def direct_mail_notification_update(doc, method):
    if doc.get("channel") in MAIL_TYPES:
        if not doc.get("message"):
            doc.message = "See the attached document."
        # clear the direct_mail_notification_doctypes cache
        frappe.cache.delete_value("direct_mail_notification_doctypes")


def trigger_daily_direct_mail_notifications():
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
        notification = DirectMailNotification("Notification", n)

        for doc in notification.get_documents_for_today():
            evaluate_alert(doc, notification, notification.event)
            frappe.db.commit()


def run_direct_mail_notifications(doc, method):
    """Run notifications for any relavant doc methods"""
    if (
        (frappe.flags.in_import and frappe.flags.mute_emails)
        or frappe.flags.in_patch
        or frappe.flags.in_install
    ):
        return

    # only run on doctypes with notifications assigned
    def _get_direct_mail_notification_doctypes():
        """returns enabled notifications for the current doctype"""

        return frappe.get_all(
            "Notification",
            fields=["unique(document_type) as document_type"],
            filters={
                "enabled": 1,
                "channel": ["in", MAIL_TYPES],
            },
            pluck="document_type",
        )

    direct_mail_notification_doctypes = frappe.cache.get_value(
        "direct_mail_notification_doctypes", _get_direct_mail_notification_doctypes
    )

    if doc.doctype not in direct_mail_notification_doctypes:
        return

    if doc.flags.direct_mail_notifications_executed is None:
        doc.flags.direct_mail_notifications_executed = []

    if doc.flags.direct_mail_notifications is None:

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

        doc.flags.direct_mail_notifications = frappe.cache.hget(
            "direct_mail_notifications", doc.doctype, _get_notifications
        )

    if not doc.flags.direct_mail_notifications:
        return

    def _evaluate_alert(notification):
        if notification.name in doc.flags.direct_mail_notifications_executed:
            return

        notification = DirectMailNotification("Notification", notification.name)

        evaluate_alert(doc, notification, notification.event)

        doc.flags.direct_mail_notifications_executed.append(notification.name)

    event_map = {
        "on_update": "Save",
        "after_insert": "New",
        "on_submit": "Submit",
        "on_cancel": "Cancel",
    }

    if not doc.flags.in_insert:
        # value change is not applicable in insert
        event_map["on_change"] = "Value Change"

    for notification in doc.flags.direct_mail_notifications:
        event = event_map.get(method, None)
        if event and notification.event == event:
            _evaluate_alert(notification)
        elif notification.event == "Method" and method == notification.method:
            _evaluate_alert(notification)
