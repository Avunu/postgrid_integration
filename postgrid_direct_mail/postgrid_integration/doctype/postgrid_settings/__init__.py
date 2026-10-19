# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

import io
import json
import pprint
from typing import Any

import frappe
import jwt

from postgrid_direct_mail.config import MAIL_TYPES

STATUS_MAP = {
	"ready": {
		"status": "Queued",
		"delivery_status": "Scheduled",
	},
	"printing": {
		"status": "Authorized",
		"delivery_status": "Sending",
	},
	"processed_for_delivery": {
		"status": "Completed",
		"delivery_status": "Sent",
	},
	"completed": {
		"status": "Completed",
		"delivery_status": "Opened",
	},
	"cancelled": {
		"status": "Cancelled",
		"delivery_status": "Rejected",
	},
}


def update_address(address_data: dict[str, Any] | None) -> None:
	if not address_data:
		return
	address_id = address_data.get("id")
	address_status = address_data.get("addressStatus")
	if not address_id or address_status != "verified":
		return
	address = frappe.db.exists("Address", {"postgrid_id": address_id})
	if address:
		address = frappe.get_doc("Address", address)
		address.update(
			{
				"address_line1": address_data.get("addressLine1"),
				"address_line2": address_data.get("addressLine2"),
				"city": address_data.get("city"),
				"state": address_data.get("provinceOrState"),
				"pincode": address_data.get("postalOrZip"),
			}
		)
		if address_data.get("companyName"):
			address.set("address_title", address_data.get("companyName"))
		address.save(ignore_permissions=True)


# PostGrid calls this webhook without a Frappe session; the body is a JWT signed with webhooks_secret,
# verified below before anything is read, and an unsigned or unregistered call is refused.
@frappe.whitelist(allow_guest=True)  # nosemgrep: rules.security.guest-whitelisted-method
def webhooks() -> int | None:
	r = frappe.request
	if not r:
		return None

	settings = frappe.get_single("PostGrid Settings")
	if not settings.webhooks_secret:
		# No secret means no webhook was ever registered, so nothing can be trusted
		raise frappe.AuthenticationError

	try:
		payload = jwt.decode(r.get_data(), settings.webhooks_secret, algorithms=["HS256"])
	except jwt.PyJWTError:
		raise frappe.AuthenticationError from None

	data: dict[str, Any] = payload["data"]

	request_id = data["id"]
	pg_status = data["status"]
	status = STATUS_MAP[pg_status]
	ig = frappe.db.exists("Integration Request", {"request_id": request_id})
	if ig:
		frappe.db.set_value("Integration Request", ig, "status", status["status"])
	com = frappe.db.exists("Communication", {"message_id": request_id})
	if com:
		frappe.db.set_value("Communication", com, "delivery_status", status["delivery_status"])
		# if the communication doesn't yet have an attachment, download and attach to the communication
		if settings.save_pdf_files:
			pdf_url = data.get("url")
			pdf_file = frappe.db.exists(
				"File",
				{"attached_to_doctype": "Communication", "attached_to_name": com},
			)
			if not pdf_file:
				# download PDF and save it
				pdf_content = frappe.utils.get_request_session().get(pdf_url).content
				pdf = frappe.get_doc(
					{
						"doctype": "File",
						"file_name": f"Letter-{request_id}.pdf",
						"attached_to_doctype": "Communication",
						"attached_to_name": com,
						"content": pdf_content,
						"is_private": 1,
					}
				)
				pdf.insert(ignore_permissions=True)
	if settings.update_addresses:
		update_address(data.get("from"))
		update_address(data.get("to"))

	return 200


@frappe.whitelist()
def get_postgrid_defaults() -> dict[str, Any]:
	settings = frappe.get_single("PostGrid Settings")
	default_options: dict[str, Any] = {}
	match settings.address_placement:
		case "Insert Blank Page":
			default_options["address_placement"] = "insert_blank_page"
		case "Top of First Page":
			default_options["address_placement"] = "top_first_page"
	match settings.envelope_type:
		case "Standard Double Window":
			default_options["envelope_type"] = "standard_double_window"
		case "Flat":
			default_options["envelope_type"] = "flat"

	default_options["misc"] = {
		"color": bool(settings.color),
		"double_sided": bool(settings.double_sided),
		"express": bool(settings.express),
	}

	return default_options


@frappe.whitelist()
def mail_letter(
	doctype: str,
	docname: str | int,
	print_format: str | None,
	from_address: str,
	to_address: str,
	to_contact: str | None = None,
	pg_parameters: str | dict[str, Any] | None = None,
	cl_print_format: str | None = None,
) -> dict[str, str]:
	params: dict[str, Any]
	if pg_parameters:
		params = json.loads(pg_parameters) if isinstance(pg_parameters, str) else pg_parameters
		misc = params.get("misc")
		if type(misc) is list:
			# The print view's MultiCheck sends the ticked options as a list
			params["misc"] = dict.fromkeys(misc, True)
	else:
		params = get_postgrid_defaults()

	from_address_doc = frappe.get_doc("Address", from_address)
	from_country = frappe.get_doc("Country", from_address_doc.get("country"))
	to_address_doc = frappe.get_doc("Address", to_address)
	# The contact comes from the print view's dialog, in pg_parameters
	to_contact_doc: Any = {}
	if params.get("to_contact"):
		to_contact_doc = frappe.get_doc("Contact", params["to_contact"])
	to_country_code = frappe.get_value("Country", to_address_doc.get("country"), "code")
	pdf_file = io.BytesIO(
		frappe.get_print(
			doctype=doctype,
			name=docname,
			print_format=print_format,
			as_pdf=True,
		)
	)

	if cl_print_format:
		cover_letter = io.BytesIO(
			frappe.get_print(
				doctype=doctype,
				name=docname,
				print_format=cl_print_format,
				as_pdf=True,
			)
		)
		# insert blank page and merge with PDF
		from pypdf import PdfReader, PdfWriter

		pdf_reader = PdfReader(pdf_file)
		cover_letter_reader = PdfReader(cover_letter)

		merged_pdf = PdfWriter()
		merged_pdf.append_pages_from_reader(cover_letter_reader)
		if params.get("misc", {}).get("double_sided"):
			merged_pdf.add_blank_page()
		merged_pdf.append_pages_from_reader(pdf_reader)

		# Create a new BytesIO object to store the merged PDF
		merged_pdf_file = io.BytesIO()
		merged_pdf.write(merged_pdf_file)

		# Reset the position of the BytesIO object to the beginning
		merged_pdf_file.seek(0)

		# Use the merged PDF file instead of the original pdf_file
		pdf_file = merged_pdf_file

	pdf_file.name = f"{doctype}-{docname}.pdf"
	# Send a letter
	client = frappe.get_single("PostGrid Settings").initialize_client()
	error = None
	from_ = {
		"company_name": from_address_doc.get("address_title"),
		"address_line1": from_address_doc.get("address_line1"),
		"address_line2": from_address_doc.get("address_line2"),
		"city": from_address_doc.get("city"),
		"province_or_state": from_address_doc.get("state"),
		"postal_or_zip": from_address_doc.get("pincode"),
		"country_code": from_country.get("code"),
	}
	to = {
		"company_name": to_address_doc.get("address_title"),
		"first_name": to_contact_doc.get("first_name"),
		"last_name": to_contact_doc.get("last_name"),
		"address_line1": to_address_doc.get("address_line1"),
		"address_line2": to_address_doc.get("address_line2"),
		"city": to_address_doc.get("city"),
		"province_or_state": to_address_doc.get("state"),
		"postal_or_zip": to_address_doc.get("pincode"),
		"country_code": to_country_code,
	}
	request = {
		"from_": from_,
		"to": to,
		"pdf": pdf_file,
		"address_placement": params.get("address_placement"),
		"envelope_type": params.get("envelope_type"),
		**params.get("misc", {}),
	}
	try:
		letter = client.Letter.create(**request)
		response = letter.__dict__
		from_obj = getattr(letter, "from")
		from_id = from_obj.id if hasattr(from_obj, "id") else None
		if from_id:
			frappe.db.set_value("Address", from_address_doc.name, "postgrid_id", from_id)
		to_id = letter.to.id if hasattr(letter.to, "id") else None
		if to_id:
			frappe.db.set_value("Address", to_address_doc.name, "postgrid_id", to_id)
	except Exception as e:
		error = e
		letter = None
		response = {"id": "error", "error": frappe.get_traceback()}

	# create integration request
	# from_address_formatted = "<br>".join(
	#     filter(
	#         None,
	#         [
	#             from_["address_line1"],
	#             from_["address_line2"],
	#             f"{from_['city']} {from_['province_or_state']} {from_['postal_or_zip']}",
	#         ],
	#     )
	# )
	to_address_formatted = "<br>".join(
		line
		for line in (
			to["address_line1"],
			to["address_line2"],
			f"{to['city']} {to['province_or_state']} {to['postal_or_zip']}",
		)
		if line
	)
	pp = pprint.PrettyPrinter(depth=4)
	ig = frappe.get_doc(
		{
			"doctype": "Integration Request",
			"integration_request_service": "PostGrid",
			"request_description": "Send Letter",
			"request_id": response.get("id"),
			"status": "Queued",
			"data": pp.pformat(request),
			"output": pp.pformat(response),
			"reference_doctype": doctype,
			"reference_docname": docname,
		}
	).insert(ignore_permissions=True)

	if error is not None or letter is None:
		ig.set("error", str(error))
		ig.set("status", "Failed")
		ig.save()
		frappe.log_error("PostGrid Error", error)
		return {
			"message": f"Failed to send letter, please check the <a href='/app/integration-request/{ig.name}' target='_blank'>Integration Request</a> for details",
			"indicator": "red",
		}

	# add to timeline
	message = f"{doctype} mailed as {print_format} to:<br>{to_address_formatted}"

	communication = frappe.get_doc(
		{
			"comment_type": "Info",
			"communication_date": frappe.utils.get_datetime_str(letter.send_date),
			"communication_type": "Mailed Letter",
			"content": message,
			"delivery_status": "Scheduled",
			"doctype": "Communication",
			"message_id": response.get("id"),
			"recipients": to_address_doc.get("address_title"),
			"reference_doctype": doctype,
			"reference_name": docname,
			"sender_full_name": "PostGrid",
			"sender": frappe.session.user_email,
			"sent_or_received": "Sent",
			"status": "Linked",
			"subject": f"{docname} Direct Mail",
			"user": frappe.session.user,
		}
	)
	communication.insert(ignore_permissions=True)

	return {
		"message": f"<a href='/app/integration-request/{ig.name}' target='_blank'>Letter sent to PostGrid</a>.",
		"indicator": "green",
	}


def get_timeline_content(doctype, docname):
	communications = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": doctype,
			"reference_name": docname,
			"communication_type": ["in", MAIL_TYPES],
		},
		fields=[
			"creation",
			"name",
			"communication_date",
			"communication_type",
			"content",
			"delivery_status",
			"message_id",
			"recipients",
		],
		order_by="creation desc",
	)

	timeline_contents = []
	for communication in communications:
		file_url = frappe.db.get_value("File", {"attached_to_name": communication.name}, "file_url")
		timeline_contents.append(
			{
				"icon": "mail",
				"is_card": True,
				"creation": communication.communication_date,
				"template": "direct_mail_timeline",
				"template_data": {
					"file_url": file_url,
					**communication,
				},
			}
		)
	return timeline_contents
