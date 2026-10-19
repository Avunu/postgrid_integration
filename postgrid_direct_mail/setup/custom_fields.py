# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

"""The custom fields the app ships, and the system-generated flag that protects them.

The fields are defined in `<module>/custom/*.json`, which frappe syncs on install and migrate and which
`frappe-types gen-registry` reads to type the desk scripts. Those files may not carry `is_system_generated`
(test_utils' `validate_customizations` rejects it), and frappe's sync inserts a new row with the flag off
and leaves an existing row's flag alone when the file doesn't name it. So the install and migrate hooks set
it here, after the sync. With the flag on, Customize Form's "Reset to Standard" keeps the fields and they
can't be renamed. `before_uninstall` removes exactly these fields.
"""

import json
from pathlib import Path

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields

APP = "postgrid_direct_mail"


def get_custom_fields() -> dict[str, list[str]]:
	"""The fieldnames of the Custom Fields the app's `custom/*.json` files ship, by DocType."""
	fields: dict[str, list[str]] = {}
	for module in frappe.get_module_list(APP):
		custom_dir = Path(frappe.get_module_path(module)) / "custom"
		for path in sorted(custom_dir.glob("*.json")):
			for field in json.loads(path.read_text()).get("custom_fields", []):
				fields.setdefault(field["dt"], []).append(field["fieldname"])
	return fields


def mark_system_generated() -> None:
	"""Turn `is_system_generated` on for the shipped fields that have it off. Idempotent."""
	custom_field = frappe.qb.DocType("Custom Field")
	for doctype, fieldnames in get_custom_fields().items():
		names = frappe.get_all(
			"Custom Field",
			filters={"dt": doctype, "fieldname": ("in", fieldnames), "is_system_generated": 0},
			pluck="name",
		)
		if not names:
			continue
		frappe.qb.update(custom_field).set(custom_field.is_system_generated, 1).where(
			custom_field.name.isin(names)
		).run()
		# Customize Form reads the flag from the cached meta
		frappe.clear_cache(doctype=doctype)


def remove_custom_fields() -> None:
	"""Delete exactly the shipped fields. Their columns and data stay, as frappe leaves dropped fields."""
	delete_custom_fields(get_custom_fields())
