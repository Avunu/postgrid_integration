# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

"""Demo data for frappe-demo and the screenshots in docs/screenshots/.

The print view's Mail button is offered on submitted documents, and the demo site has no ERPNext, so
the demo adds a small submittable DocType, Customer Statement, with the link fields the mail dialog
reads its defaults from (`company_address`, `customer_address`, `contact_person`). It then:

- fills in PostGrid Settings in Test mode, written straight to the database as the tests do, so no
  webhook is registered;
- submits three statements and mails two of them through the app's own `mail_letter`, with PostGrid's
  client and the PDF renderer replaced by stand-ins, so nothing leaves the site. Their delivery status
  is then set the way PostGrid's webhook sets it;
- adds a Mailed Letter notification that mails each statement when it is submitted.
"""

import datetime
import io
from typing import Any
from unittest.mock import patch

import frappe
import postgrid
from frappe.utils.password import set_encrypted_password
from pypdf import PdfWriter

from postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings import STATUS_MAP, mail_letter

DOCTYPE = "Customer Statement"
PRINT_FORMAT = "Statement Letter"
NOTIFICATION = "Mail Statements on Submit"

# name, customer, address line, city, state, zip, contact (first, last), amount due
STATEMENTS = (
	("STMT-0001", "Lakeside Bakery", "48 Harbor Road", "Erie", "PA", "16507", ("Dana", "Whitfield"), 1240.50),
	("STMT-0002", "Northwind Clinic", "300 Elm Avenue", "Akron", "OH", "44308", ("Ravi", "Menon"), 862.00),
	(
		"STMT-0003",
		"Maple Street Hardware",
		"12 Maple Street",
		"Lancaster",
		"PA",
		"17603",
		("Lena", "Ortiz"),
		3415.75,
	),
)

# The mailed statements: how many days before the demo day they went out, and PostGrid's status now.
MAILED = {"STMT-0001": (12, "completed"), "STMT-0002": (4, "processed_for_delivery")}

STATEMENT_HTML = """<div style="font-size: 13px; line-height: 1.6">
<p><strong>Harbor Supply Co.</strong><br>1 Commerce Drive<br>Pittsburgh PA 15222</p>
<h2 style="margin-top: 32px">Statement of Account</h2>
<p>{{ doc.customer_name }}<br>Statement date: {{ frappe.utils.formatdate(doc.statement_date) }}</p>
<table class="table table-bordered">
<tr><th>Amount due</th><th>Due date</th></tr>
<tr><td>{{ doc.get_formatted("amount_due") }}</td><td>{{ frappe.utils.formatdate(doc.due_date) }}</td></tr>
</table>
<p>Please send payment by the due date. Thank you for your business.</p>
</div>"""


def make_statement_doctype() -> None:
	if frappe.db.exists("DocType", DOCTYPE):
		return
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": DOCTYPE,
			"module": "PostGrid Integration",
			"custom": 1,
			"is_submittable": 1,
			"autoname": "Prompt",
			"title_field": "customer_name",
			"fields": [
				{"fieldname": "customer_name", "fieldtype": "Data", "label": "Customer", "in_list_view": 1},
				{
					"fieldname": "customer_address",
					"fieldtype": "Link",
					"label": "Customer Address",
					"options": "Address",
				},
				{
					"fieldname": "contact_person",
					"fieldtype": "Link",
					"label": "Contact",
					"options": "Contact",
				},
				{
					"fieldname": "company_address",
					"fieldtype": "Link",
					"label": "Company Address",
					"options": "Address",
				},
				{"fieldname": "column_break_amounts", "fieldtype": "Column Break"},
				{"fieldname": "statement_date", "fieldtype": "Date", "label": "Statement Date"},
				{"fieldname": "due_date", "fieldtype": "Date", "label": "Due Date"},
				{
					"fieldname": "amount_due",
					"fieldtype": "Currency",
					"label": "Amount Due",
					"in_list_view": 1,
				},
			],
			"permissions": [
				{
					"role": "System Manager",
					"read": 1,
					"write": 1,
					"create": 1,
					"submit": 1,
					"cancel": 1,
					"print": 1,
				}
			],
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Print Format",
			"name": PRINT_FORMAT,
			"doc_type": DOCTYPE,
			"module": "PostGrid Integration",
			"standard": "No",
			"custom_format": 1,
			"print_format_type": "Jinja",
			"html": STATEMENT_HTML,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("DocType", DOCTYPE, "default_print_format", PRINT_FORMAT)
	frappe.clear_cache(doctype=DOCTYPE)


def configure_settings() -> None:
	"""Test mode with a placeholder key, as a saved form leaves it, and no call to PostGrid."""
	set_encrypted_password("PostGrid Settings", "PostGrid Settings", "test_sk_demo", "pm_key_test")
	values = {
		"mode": "Test",
		"pm_key_test": "*" * 12,
		"webhook_id_test": "webhook_demo_test",
		"webhooks_secret": "demo-webhook-secret",
		"update_addresses": 1,
		"save_pdf_files": 1,
		"address_placement": "Insert Blank Page",
		"envelope_type": "Standard Double Window",
		"double_sided": 1,
		"color": 0,
		"express": 0,
	}
	for fieldname, value in values.items():
		frappe.db.set_single_value("PostGrid Settings", fieldname, value)
	frappe.clear_document_cache("PostGrid Settings", "PostGrid Settings")


def make_address(title: str, line1: str, city: str, state: str, pincode: str) -> str:
	"""The address under its natural name, "<title>-Billing", which the mail dialog shows."""
	name = f"{title}-Billing"
	if not frappe.db.exists("Address", name):
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": title,
				"address_type": "Billing",
				"address_line1": line1,
				"city": city,
				"state": state,
				"pincode": pincode,
				"country": "United States",
			}
		).insert(ignore_permissions=True)
	return name


def make_contact(first: str, last: str, company: str, address: str) -> str:
	"""The contact under its natural name, "<first> <last>"."""
	name = f"{first} {last}"
	if not frappe.db.exists("Contact", name):
		frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": first,
				"last_name": last,
				"company_name": company,
				"address": address,
			}
		).insert(ignore_permissions=True)
	return name


def blank_pdf(**_: Any) -> bytes:
	writer = PdfWriter()
	writer.add_blank_page(width=612, height=792)
	buffer = io.BytesIO()
	writer.write(buffer)
	return buffer.getvalue()


def mail_statement(
	name: str, sender: str, address: str, contact: str, today: datetime.date, days_ago: int, status: str
) -> None:
	"""Mail the statement with the app's `mail_letter`, then set the status PostGrid's webhook would."""
	letter_id = f"letter_demo_{name.lower().replace('-', '_')}"
	sent = datetime.datetime.combine(today - datetime.timedelta(days=days_ago), datetime.time(10, 30))
	letter = postgrid.Letter(
		id=letter_id,
		object="letter",
		status="ready",
		send_date=sent.isoformat(),
		to=postgrid.Contact(id=f"contact_{letter_id}", object="contact"),
		**{"from": postgrid.Contact(id="contact_demo_sender", object="contact")},
	)
	with (
		patch.object(postgrid.Letter, "create", return_value=letter),
		patch("frappe.get_print", side_effect=blank_pdf),
	):
		mail_letter(
			doctype=DOCTYPE,
			docname=name,
			print_format=PRINT_FORMAT,
			from_address=sender,
			to_address=address,
			pg_parameters={
				"to_contact": contact,
				"address_placement": "insert_blank_page",
				"envelope_type": "standard_double_window",
				"misc": {"double_sided": True, "color": False, "express": False},
			},
		)
	mapped = STATUS_MAP[status]
	request = frappe.db.get_value("Integration Request", {"request_id": letter_id})
	frappe.db.set_value("Integration Request", request, "status", mapped["status"])
	communication = frappe.db.get_value("Communication", {"message_id": letter_id})
	frappe.db.set_value("Communication", communication, "delivery_status", mapped["delivery_status"])


def make_notification(sender: str) -> None:
	if frappe.db.exists("Notification", NOTIFICATION):
		return
	frappe.get_doc(
		{
			"doctype": "Notification",
			"name": NOTIFICATION,
			"subject": NOTIFICATION,
			"document_type": DOCTYPE,
			"event": "Submit",
			"channel": "Mailed Letter",
			# what the form's script sets for a mail channel, so the form opens unchanged
			"attach_print": 1,
			"print_format": PRINT_FORMAT,
			"from_address": sender,
			"to_address_document_field": "customer_address",
			"to_contact_document_field": "contact_person",
			"address_placement": "Insert Blank Page",
			"envelope_type": "Standard Double Window",
			"double_sided": 1,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)


def setup(ctx: dict[str, Any]) -> None:
	"""Create the demo once; every date is taken from `ctx["today"]`."""
	today: datetime.date = ctx["today"]
	make_statement_doctype()
	configure_settings()
	sender = make_address("Harbor Supply Co.", "1 Commerce Drive", "Pittsburgh", "PA", "15222")
	for name, customer, line1, city, state, pincode, (first, last), amount in STATEMENTS:
		if frappe.db.exists(DOCTYPE, name):
			continue
		address = make_address(customer, line1, city, state, pincode)
		contact = make_contact(first, last, customer, address)
		statement = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"customer_name": customer,
				"company_address": sender,
				"customer_address": address,
				"contact_person": contact,
				"statement_date": frappe.utils.add_days(today, -14),
				"due_date": frappe.utils.add_days(today, 16),
				"amount_due": amount,
			}
		)
		statement.insert(ignore_permissions=True, set_name=name)
		statement.submit()
		if name in MAILED:
			days_ago, status = MAILED[name]
			mail_statement(name, sender, address, contact, today, days_ago, status)
	make_notification(sender)
