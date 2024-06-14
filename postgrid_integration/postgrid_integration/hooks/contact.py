# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

# ATTEMPT TO SYNC CONTACTS WITH POSTGRID, DISGARDED FOR NOW, AS THE POSTGRID API DOES NOT SUPPORT UPDATING CONTACTS

import frappe

from frappe.contacts.doctype.address.address import get_preferred_address

def sync_contact(doc, method):
    if not doc.address:
        for link in doc.links:
            if link.link_doctype == "Customer":
                doc.address = get_preferred_address("Customer", link.link_name, "is_shipping_address")
                break
            elif link.link_doctype == "Supplier":
                doc.address = get_preferred_address("Supplier", link.link_name, "is_shipping_address")
                break
            elif link.link_doctype == "Company":
                doc.address = get_preferred_address("Company", link.link_name, "is_shipping_address")
                break
    if doc.address:
        address = frappe.get_doc("Address", doc.address)
        country_code = frappe.get_value("Country", address.get("country"), "code")
    else:
        return
    client = frappe.get_single("PostGrid Settings").initialize_client()
    contact_data = {
        "first_name": doc.get("first_name"),
        "last_name": doc.get("last_name"),
        "company_name": doc.get("company_name") or address.get("address_title"),
        "job_title": doc.get("designation"),
        "email": doc.get("email_id"),
        "phone": doc.get("mobile_no"),
        "address_line1": address.get("address_line1"),
        "address_line2": address.get("address_line2"),
        "city": address.get("city"),
        "province_or_state": address.get("state"),
        "postal_or_zip": address.get("pincode"),
        "country_code": country_code
    }
    try:
        if doc.postgrid_id:
            contact_data["id"] = doc.postgrid_id
            contact = client._pm_post(f"contacts/{doc.postgrid_id}", **contact_data)
        else:
            contact = client.Contact.create(**contact_data)
            doc.postgrid_id = contact.id
    except Exception as e:
        frappe.throw(str(e))
