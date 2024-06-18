# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

import frappe
import io
import json
import pprint
import jwt
from postgrid_integration.config import MAIL_TYPES

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


@frappe.whitelist(allow_guest=True)
def webhooks():
    r = frappe.request
    if not r:
        return

    settings = frappe.get_single("PostGrid Settings")

    try:
        data = jwt.decode(
            r.get_data(), settings.webhooks_secret, algorithms=["HS256"]
        ).get("data")
    except jwt.InvalidSignatureError:
        raise frappe.AuthenticationError

    request_id = data["id"]
    pg_status = data["status"]
    status = STATUS_MAP[pg_status]
    ig = frappe.db.exists("Integration Request", {"request_id": request_id})
    if ig:
        frappe.db.set_value("Integration Request", ig, "status", status["status"])
    com = frappe.db.exists("Communication", {"message_id": request_id})
    if com:
        frappe.db.set_value(
            "Communication", com, "delivery_status", status["delivery_status"]
        )
        # if the communication doesn't yet have an attachment, download and attach to the communication
        pdf_url = data.get("url")
        pdf_file =  frappe.db.exists("File", {"attached_to_doctype": "Communication", "attached_to_name": com})
        if not pdf_file:
            pdf = frappe.get_doc(
                {
                    "doctype": "File",
                    "file_url": pdf_url,
                    "file_name": f"Letter-{request_id}.pdf",
                    "attached_to_doctype": "Communication",
                    "attached_to_name": com,
                }
            )
            pdf.insert(ignore_permissions=True)
    if settings.update_addresses:
        update_address(data.get("from"))
        update_address(data.get("to"))

    return 200


def update_address(address_data):
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
            address.address_title = address_data.get("companyName")
        address.save(ignore_permissions=True)


@frappe.whitelist()
def get_postgrid_defaults():
    settings = frappe.get_single("PostGrid Settings")
    default_options = {}
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
        "color": True if settings.color else False,
        "double_sided": True if settings.double_sided else False,
        "express": True if settings.express else False,
    }

    return default_options


@frappe.whitelist()
def mail_letter(
    doctype,
    docname,
    print_format,
    from_address,
    to_address,
    to_contact=None,
    pg_parameters=None,
    cl_print_format=None,
):
    if pg_parameters:
        if type(pg_parameters) == str:
            pg_parameters = json.loads(pg_parameters)
        misc = pg_parameters.get("misc")
        if type(misc) == list:
            pg_parameters["misc"] = {}
            for option in misc:
                pg_parameters["misc"][option] = True
    else:
        pg_parameters = get_postgrid_defaults()

    from_address = frappe.get_doc("Address", from_address)
    from_country = frappe.get_doc("Country", from_address.get("country"))
    to_address = frappe.get_doc("Address", to_address)
    to_contact = {}
    if pg_parameters.get("to_contact"):
        to_contact = frappe.get_doc("Contact", pg_parameters.get("to_contact"))
    to_country_code = frappe.get_value("Country", to_address.get("country"), "code")
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
        if pg_parameters.get("misc", {}).get("double_sided"):
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
    client = frappe.get_single("PostGrid Settings").client
    error = None
    from_ = {
        "company_name": from_address.get("address_title"),
        "address_line1": from_address.get("address_line1"),
        "address_line2": from_address.get("address_line2"),
        "city": from_address.get("city"),
        "province_or_state": from_address.get("state"),
        "postal_or_zip": from_address.get("pincode"),
        "country_code": from_country.get("code"),
    }
    to = {
        "company_name": to_address.get("address_title"),
        "first_name": to_contact.get("first_name"),
        "last_name": to_contact.get("last_name"),
        "address_line1": to_address.get("address_line1"),
        "address_line2": to_address.get("address_line2"),
        "city": to_address.get("city"),
        "province_or_state": to_address.get("state"),
        "postal_or_zip": to_address.get("pincode"),
        "country_code": to_country_code,
    }
    request = {
        "from_": from_,
        "to": to,
        "pdf": pdf_file,
        "address_placement": pg_parameters.get("address_placement"),
        "envelope_type": pg_parameters.get("envelope_type"),
        **pg_parameters.get("misc"),
    }
    try:
        letter = client.Letter.create(**request)
        response = letter.__dict__
        from_obj = getattr(letter, "from")
        from_id = from_obj.id if hasattr(from_obj, "id") else None
        if from_id:
            frappe.db.set_value("Address", from_address.name, "postgrid_id", from_id)
        to_id = letter.to.id if hasattr(letter.to, "id") else None
        if to_id:
            frappe.db.set_value("Address", to_address.name, "postgrid_id", to_id)
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
        filter(
            None,
            [
                to["address_line1"],
                to["address_line2"],
                f"{to['city']} {to['province_or_state']} {to['postal_or_zip']}",
            ],
        )
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

    if error:
        ig.error = error
        ig.status = "Failed"
        ig.save()
        frappe.log_error("PostGrid Error", error)
        return {
            "message": f"Failed to send letter, please check the <a href='/app/integration-request/{ig.name}' target='_blank'>Integration Request</a> for details",
            "indicator": "red",
        }

    # add to timeline
    message = (
        f'{doctype} mailed as {print_format} to:<br>'
        f"{to_address_formatted}"
    )
    
    communication = frappe.get_doc(
        {
            "comment_type": "Info",
            "communication_date": frappe.utils.get_datetime_str(letter.send_date),
            "communication_type": "Mailed Letter",
            "content": message,
            "delivery_status": "Error" if error else "Scheduled",
            "doctype": "Communication",
            "message_id": response.get("id"),
            "recipients": to_address.get("address_title"),
            "reference_doctype": doctype,
            "reference_name": docname,
            "sender_full_name": "PostGrid",
            "sender": frappe.session.user_email,
            "sent_or_received": "Sent",
            "status": "Linked",
            "subject": "Letter Sent",
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
        timeline_contents.append(
            {
                "icon": "mail",
                "is_card": True,
                "creation": communication.communication_date,
                "template": "direct_mail_timeline",
                "template_data": communication,
            }
        )
    return timeline_contents
