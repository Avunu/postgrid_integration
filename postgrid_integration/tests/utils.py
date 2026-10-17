# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

"""Fixtures for the app's tests. Nothing here reaches PostGrid: the tests patch the client."""

import io
from typing import Any

import frappe
import postgrid
from pypdf import PdfReader, PdfWriter


def make_pdf(pages: int = 1) -> bytes:
	writer = PdfWriter()
	for _ in range(pages):
		writer.add_blank_page(width=612, height=792)
	buffer = io.BytesIO()
	writer.write(buffer)
	return buffer.getvalue()


def count_pages(pdf: Any) -> int:
	pdf.seek(0)
	return len(PdfReader(pdf).pages)


def make_address(title: str, **values: Any) -> str:
	address = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": title,
			"address_type": "Office",
			"address_line1": values.pop("address_line1", "1 Main Street"),
			"city": values.pop("city", "Lancaster"),
			"state": values.pop("state", "PA"),
			"pincode": values.pop("pincode", "17601"),
			"country": values.pop("country", "United States"),
			**values,
		}
	).insert(ignore_permissions=True)
	return str(address.name)


def make_contact(first_name: str, last_name: str, address: str | None = None) -> str:
	contact = frappe.get_doc(
		{"doctype": "Contact", "first_name": first_name, "last_name": last_name, "address": address}
	).insert(ignore_permissions=True)
	return str(contact.name)


def make_letter(letter_id: str = "letter_test", **values: Any) -> postgrid.Letter:
	"""A Letter as postgrid-python 1.x returns it from `Letter.create`."""
	return postgrid.Letter(
		id=letter_id,
		object="letter",
		status="ready",
		send_date=values.pop("send_date", "2026-10-16T12:00:00.000Z"),
		to=postgrid.Contact(id=values.pop("to_id", "contact_to"), object="contact"),
		**{"from": postgrid.Contact(id=values.pop("from_id", "contact_from"), object="contact")},
		**values,
	)


def rollback_after_test(test: Any, name: str = "postgrid_test") -> None:
	"""Undo the test's writes when it ends. IntegrationTestCase rolls back only once per class."""
	frappe.db.savepoint(name)
	test.addCleanup(frappe.db.rollback, save_point=name)


def make_request(body: bytes) -> Any:
	"""A POST request with this body, to stand in for frappe.request."""
	from werkzeug.test import EnvironBuilder
	from werkzeug.wrappers import Request

	return Request(EnvironBuilder(method="POST", data=body, base_url="http://localhost/").get_environ())


def set_settings(**values: Any) -> None:
	"""Write PostGrid Settings straight to the database, without validate's webhook calls."""
	for fieldname, value in values.items():
		if fieldname.startswith("pm_key_"):
			from frappe.utils.password import set_encrypted_password

			set_encrypted_password("PostGrid Settings", "PostGrid Settings", value, fieldname)
			# what a saved form leaves in the field, so a later save keeps the stored key
			frappe.db.set_single_value("PostGrid Settings", fieldname, "*" * len(value))
		else:
			frappe.db.set_single_value("PostGrid Settings", fieldname, value)
	frappe.clear_document_cache("PostGrid Settings", "PostGrid Settings")
