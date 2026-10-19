# Copyright (c) 2024, Avunu LLC and contributors
# For license information, please see license.txt

"""Install, migrate and uninstall hooks.

These run inside the transaction that frappe's installer, migrator and uninstaller commit, so none of
them commits on its own.
"""

import json

import frappe

from postgrid_direct_mail.config import MAIL_TYPES
from postgrid_direct_mail.setup.custom_fields import mark_system_generated, remove_custom_fields


def add_workspace_card_link(
	workspace_name: str, card_name: str, link_type: str, link_to: str, link_label: str | None = None
) -> None:
	workspace = frappe.get_doc("Workspace", workspace_name)

	# Check if the card already exists
	card_exists = frappe.db.exists(
		"Workspace Link",
		{
			"label": card_name,
			"parent": workspace_name,
			"parenttype": "Workspace",
			"type": "Card Break",
		},
	)

	if not card_exists:
		# Create a new card link
		card = workspace.append(
			"links",
			{
				"label": card_name,
				"type": "Card Break",
			},
		)

		# Update the Workspace content
		content = json.loads(workspace.get("content") or "[]")
		content.append({"id": card.name, "type": "card", "data": {"card_name": card_name, "col": 4}})
		workspace.set("content", json.dumps(content))

	# Create a new link under the card
	workspace.append(
		"links",
		{
			"label": link_label or link_to,
			"link_to": link_to,
			"link_type": link_type,
			"type": "Link",
		},
	)

	workspace.save()


def get_docfield_options(doctype: str, field_name: str) -> list[str]:
	docfield_options = frappe.db.get_value(
		"DocField", {"parent": doctype, "fieldname": field_name}, "options"
	)
	return str(docfield_options).split("\n") if docfield_options else []


def get_options_setter(doctype: str, field_name: str) -> frappe._dict | None:
	"""The Property Setter that overrides the field's options, if there is one."""
	property_setter = frappe.qb.DocType("Property Setter")
	existing_setter = (
		frappe.qb.from_(property_setter)
		.select("name", "value")
		.where(
			(property_setter.doc_type == doctype)
			& (property_setter.field_name == field_name)
			& (property_setter.property == "options")
		)
		.limit(1)
	).run(as_dict=True)
	return existing_setter[0] if existing_setter else None


def add_field_options(doctype: str, field_name: str, options_to_add: list[str]) -> None:
	# Check for the DocField
	if not frappe.get_meta(doctype).get_field(field_name):
		return

	existing_setter = get_options_setter(doctype, field_name)
	existing_options = (
		str(existing_setter.value).split("\n")
		if existing_setter
		else get_docfield_options(doctype, field_name)
	)
	# Append in order, so the field keeps its own options first and in their order
	new_options = existing_options + [option for option in options_to_add if option not in existing_options]
	if new_options == existing_options:
		return

	if existing_setter:
		frappe.db.set_value("Property Setter", existing_setter.name, "value", "\n".join(new_options))
	else:
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


def add_mail_types() -> None:
	# Add Communication Types to the Notification and Communication Doctypes
	add_field_options("Notification", "channel", MAIL_TYPES)
	add_field_options("Communication", "communication_type", MAIL_TYPES)


def after_install() -> None:
	# Add PostGrid Settings to the Integrations Workspace
	add_workspace_card_link("Integrations", "Direct Mail", "DocType", "PostGrid Settings")
	# A new site gets the mail channels now rather than at its first migrate
	add_mail_types()


def after_migrate() -> None:
	# frappe has synced custom/*.json by now, and a field it inserted has the flag off
	mark_system_generated()
	add_mail_types()


def after_sync() -> None:
	"""On install, frappe syncs custom/*.json after the after_install hooks and before these."""
	mark_system_generated()


def revert_field_options(doctype: str, field_name: str, options_to_remove: list[str]) -> None:
	# Check for the DocField
	if not frappe.get_meta(doctype).get_field(field_name):
		return

	existing_setter = get_options_setter(doctype, field_name)
	if not existing_setter:
		return

	existing_options = str(existing_setter.value).split("\n")
	new_options = [option for option in existing_options if option not in options_to_remove]
	if new_options == existing_options:
		return

	if set(new_options) == set(get_docfield_options(doctype, field_name)):
		frappe.delete_doc("Property Setter", existing_setter.name)
	else:
		frappe.db.set_value("Property Setter", existing_setter.name, "value", "\n".join(new_options))


def remove_workspace_card_link(workspace_name: str, card_name: str, link_to: str) -> None:
	"""Remove the link, and the card when no link is left under it, from the workspace document.

	Working on the document rather than deleting `Workspace Link` rows keeps `save()` from writing the
	deleted rows back.
	"""
	if not frappe.db.exists("Workspace", workspace_name):
		return
	workspace = frappe.get_doc("Workspace", workspace_name)

	all_links = workspace.get("links")
	links = [link for link in all_links if not (link.type == "Link" and link.link_to == link_to)]

	card_index = next(
		(i for i, link in enumerate(links) if link.type == "Card Break" and link.label == card_name), None
	)
	if card_index is not None:
		next_link = links[card_index + 1] if card_index + 1 < len(links) else None
		if next_link is None or next_link.type == "Card Break":
			del links[card_index]
			content = json.loads(workspace.get("content") or "[]")
			content = [block for block in content if block.get("data", {}).get("card_name") != card_name]
			workspace.set("content", json.dumps(content))

	if len(links) == len(all_links):
		return
	workspace.set("links", links)
	workspace.save()


def before_uninstall() -> None:
	# Remove PostGrid Settings from the Integrations Workspace
	remove_workspace_card_link("Integrations", "Direct Mail", "PostGrid Settings")
	# Remove Communication Types from the Notification and Communication Doctypes
	revert_field_options("Notification", "channel", MAIL_TYPES)
	revert_field_options("Communication", "communication_type", MAIL_TYPES)
	remove_custom_fields()
