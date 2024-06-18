# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

import frappe
import json


MAIL_TYPES = [
    "Mailed Letter",
    # "Postcard" # Uncomment this after Postcard sending is implemented
    # "Cheque" # Uncomment this after Cheque sending is implemented
]


def after_install():
    # Add PostGrid Settings to the Integrations Workspace
    add_workspace_card_link("Integrations", "Direct Mail", "DocType", "PostGrid Settings")


def after_uninstall():
    # Remove PostGrid Settings from the Integrations Workspace
    remove_workspace_card_link("Integrations", "Direct Mail", "PostGrid Settings")
    # Remove Communication Types from the Notification and Communication Doctypes
    revert_field_options("Notification", "channel", MAIL_TYPES)
    revert_field_options("Communication", "communication_type", MAIL_TYPES)


def after_migrate():
    # Add Communication Types from the Notification and Communication Doctypes
    add_field_options("Notification", "channel", MAIL_TYPES)
    add_field_options("Communication", "communication_type", MAIL_TYPES)


def add_field_options(doctype, field_name, options_to_add):
    print(f"Adding {options_to_add} to {doctype}.{field_name}")
    # Check for the DocField
    docfield = frappe.get_meta(doctype).get_field(field_name)
    if not docfield:
        print(f"DocField {field_name} not found in {doctype}")
        return
    # Check if a property setter exists for the field's options
    Property_Setter_doctype = frappe.qb.DocType("Property Setter")
    existing_setter = (
        frappe.qb.from_(Property_Setter_doctype)
        .select("name", "value")
        .where(
            (Property_Setter_doctype.doc_type == doctype)
            & (Property_Setter_doctype.field_name == field_name)
            & (Property_Setter_doctype.property == "options")
        )
        .limit(1)
    ).run(as_dict=True)

    if existing_setter:
        print(f"Existing Property Setter found for {doctype}.{field_name}")
        existing_options = set(existing_setter[0].value.split("\n"))
        new_options = existing_options.union(options_to_add)
        if new_options != existing_options:
            frappe.db.set_value(
                "Property Setter",
                existing_setter[0].name,
                "value",
                "\n".join(new_options),
            )
            
    else:
        print(f"No Property Setter found for {doctype}.{field_name}")
        docfield_options = get_docfield_options(doctype, field_name)
        new_options = docfield_options.union(options_to_add)
        if new_options != docfield_options:
            frappe.make_property_setter(
                {
                    "doctype": doctype,
                    "doctype_or_field": "DocField",
                    "fieldname": field_name,
                    "property": "options",
                    "value": "\n".join(new_options),
                    "property_type": "Text",
                },
                is_system_generated=True,
            )
    frappe.db.commit()


def revert_field_options(doctype, field_name, options_to_remove):
    # Check for the DocField
    docfield = frappe.get_meta(doctype).get_field(field_name)
    if not docfield:
        return
    # Check if a property setter exists for the field's options
    Property_Setter_doctype = frappe.qb.DocType("Property Setter")
    existing_setter = (
        frappe.qb.from_(Property_Setter_doctype)
        .select("name", "value")
        .where(
            (Property_Setter_doctype.doc_type == doctype)
            & (Property_Setter_doctype.field_name == field_name)
            & (Property_Setter_doctype.property == "options")
        )
        .limit(1)
    ).run(as_dict=True)

    if existing_setter:
        existing_options = set(existing_setter[0].value.split("\n"))
        new_options = existing_options - set(options_to_remove)
        if new_options != existing_options:
            docfield_options = get_docfield_options(doctype, field_name)
            if new_options == docfield_options:
                frappe.delete_doc("Property Setter", existing_setter[0].name)
            else:
                frappe.db.set_value(
                    "Property Setter",
                    existing_setter[0].name,
                    "value",
                    "\n".join(new_options),
                )
    frappe.db.commit()


def get_docfield_options(doctype, field_name):
    docfield_options = frappe.db.get_value('DocField', {'parent': doctype, 'fieldname': field_name}, 'options')
    if docfield_options:
        return set(docfield_options.split("\n"))
    else:
        return set()


def add_workspace_card_link(workspace_name, card_name, link_type, link_to, link_label=None):
    workspace = frappe.get_doc("Workspace", workspace_name)
    
    # Check if the card already exists
    card_exists = frappe.db.exists("Workspace Link", {
        "label": card_name,
        "parent": workspace_name,
        "parenttype": "Workspace",
        "type": "Card Break",
    })
    
    if not card_exists:
        # Create a new card link
        card = workspace.append("links", {
            "label": card_name,
            "type": "Card Break",
        })
    
        # Update the Workspace content
        content = json.loads(workspace.content)
        content.append({
            "id": card.name,
            "type": "card",
            "data": {
                "card_name": card_name,
                "col": 4
            }
        })
        workspace.content = json.dumps(content)
    
    # Create a new link under the card
    workspace.append("links", {
        "label": link_label or link_to,
        "link_to": link_to,
        "link_type": link_type,
        "type": "Link",
    })
    
    workspace.save()
    frappe.db.commit()


def remove_workspace_card_link(workspace_name, card_name, link_to):
    workspace = frappe.get_doc("Workspace", workspace_name)
    
    # Remove the link from the Workspace Link table
    link_exists = frappe.db.exists("Workspace Link", {
        "parent": workspace_name,
        "parenttype": "Workspace",
        "type": "Link",
        "link_to": link_to
    })
    
    if link_exists:
        frappe.db.delete("Workspace Link", link_exists)
    
    # Check if the card has any remaining links
    card_link = frappe.db.exists("Workspace Link", {
        "parent": workspace_name,
        "parenttype": "Workspace",
        "type": "Card Break",
        "label": card_name
    })
    
    if card_link:
        card_links = frappe.get_all("Workspace Link", filters={
            "parent": workspace_name,
            "parenttype": "Workspace"
        }, order_by="idx asc")
        
        card_index = next((i for i, link in enumerate(card_links) if link.name == card_link), -1)
        
        if card_index != -1:
            has_links = False
            
            if card_index < len(card_links) - 1:
                next_link = card_links[card_index + 1]
                has_links = next_link.type != "Card Break"
            
            if not has_links:
                # Remove the card from the Workspace Link table
                frappe.db.delete("Workspace Link", card_link)
                
                # Update the Workspace content
                content = json.loads(workspace.content)
                content = [block for block in content if block["data"].get("card_name") != card_name]
                workspace.content = json.dumps(content)
                workspace.save()
    
    frappe.db.commit()