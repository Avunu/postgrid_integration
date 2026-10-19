// Copyright (c) 2026, Avunu LLC and contributors
// For license information, please see license.txt

/**
 * The channels this app adds to Notification. A property setter adds them to `channel` on migrate,
 * so the generated registry, which reads only the shipped JSON, doesn't list them.
 * @type {ReadonlySet<string | null | undefined>}
 */
const MAIL_TYPES = new Set(["Mailed Letter", "Postcard", "Cheque"]);

frappe.ui.form.on("Notification", {
	onload(frm) {
		// if channel is already set, trigger the channel event
		if (frm.doc.channel) {
			void frm.trigger("channel");
		}
	},
	channel(frm) {
		if (MAIL_TYPES.has(frm.doc.channel)) {
			// hide the fields that are not required for mailed notifications
			frm.set_df_property("column_break_5", "hidden", 1);
			frm.set_df_property("message_sb", "hidden", 1);
			const attachment_settings = frm.fields_dict["column_break_25"];
			if (attachment_settings && is_collapsed_section(attachment_settings)) {
				attachment_settings.collapse();
			}
			void frm.set_value("attach_print", 1);
			frm.set_df_property("attach_print", "hidden", 1);
			frm.set_df_property("print_format", "hidden", 0);
			// if from address is missing and ERPNext is installed, get the default company address
			if (!frm.doc.from_address) {
				const company = frappe.defaults.get_user_default("Company");
				// exit if company is not set
				if (company) {
					void frappe.call({
						method: "erpnext.setup.doctype.company.company.get_default_company_address",
						args: { name: company },
						debounce: 2000,
						callback(r) {
							void frm.set_value("from_address", typeof r?.message === "string" ? r.message : "");
						},
					});
				}
			}
		} else {
			// show the fields that are required for non-mailed notifications
			frm.set_df_property("message_sb", "hidden", 0);
			frm.set_df_property("column_break_5", "hidden", 0);
			frm.set_df_property("column_break_25", "collapsible", 1);
			frm.set_df_property("attach_print", "hidden", 0);
		}
		if (frm.doc.document_type) {
			setup_mailing_document_field_select(frm);
		}
	},
	document_type(frm) {
		// populate the to_address_document_field options
		setup_mailing_document_field_select(frm);
		// set the query on the cl_print_format field
		if (frm.doc.document_type) {
			frm.set_query("cl_print_format", () => ({
				filters: {
					doc_type: frm.doc.document_type,
				},
			}));
		}
	},
});

/**
 * Whether a section is collapsible and collapsed: frappe's section control has `is_collapsed()`
 * and `collapse()`, which the field's control type doesn't declare.
 * @param {unknown} section
 * @returns {section is { is_collapsed(): boolean; collapse(): void }}
 */
function is_collapsed_section(section) {
	return (
		typeof section === "object" &&
		section !== null &&
		"is_collapsed" in section &&
		typeof section.is_collapsed === "function" &&
		"collapse" in section &&
		typeof section.collapse === "function" &&
		Boolean(section.is_collapsed())
	);
}

/**
 * Populate the to_address_document_field and to_contact_document_field options with the
 * document type's Address and Contact links.
 * @param {frappe.ui.form.Form<"Notification">} frm
 */
function setup_mailing_document_field_select(frm) {
	/**
	 * @param {import("frappe-types").DocField} df
	 * @param {string} [parent_field] the Table field, for a child table's field
	 * @returns {{ value: string; label: string }}
	 */
	const get_select_options = (df, parent_field) => {
		// Append parent_field name along with fieldname for child table fields
		const select_value = parent_field ? `${df.fieldname},${parent_field}` : df.fieldname;

		return {
			value: select_value,
			label: `${df.fieldname} (${__(df.label ?? "", undefined, df.parent)})`,
		};
	};

	const document_type = frm.doc.document_type;
	// Check if the selected channel is in the MAIL_TYPES set
	if (document_type && MAIL_TYPES.has(frm.doc.channel)) {
		frappe.model.with_doctype(document_type, () => {
			const fields = frappe.get_meta(document_type)?.fields ?? [];
			/** @param {string} options */
			const link_options = (options) =>
				fields
					.filter((d) => d.options === options && d.fieldtype === "Link")
					.map((d) => get_select_options(d));

			// Update the receiver_by_document_field options
			frm.set_df_property("to_address_document_field", "options", ["", ...link_options("Address")]);
			frm.set_df_property("to_contact_document_field", "options", ["", ...link_options("Contact")]);
		});
	}
}
