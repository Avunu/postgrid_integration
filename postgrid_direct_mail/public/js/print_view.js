// Copyright (c) 2026, Avunu LLC and contributors
// For license information, please see license.txt

/**
 * What `get_postgrid_defaults` returns: the PostGrid Settings defaults, in PostGrid's terms.
 * @typedef {object} PostGridDefaults
 * @property {"insert_blank_page" | "top_first_page"} [address_placement]
 * @property {"standard_double_window" | "flat"} [envelope_type]
 * @property {{ color: boolean; double_sided: boolean; express: boolean }} misc
 */

/**
 * The mail dialog's values.
 * @typedef {object} MailLetterValues
 * @property {string} from_address
 * @property {string} to_address
 * @property {string} [to_contact]
 * @property {string} address_placement
 * @property {string} envelope_type
 * @property {string[]} [misc]
 * @property {0 | 1} [with_cover_letter]
 * @property {string} [cl_print_format]
 */

/** @typedef {{ message: string; indicator: string }} MailLetterResult */

/** @typedef {frappe.Doc<frappe.DocType> & Record<string, unknown>} PrintedDoc */

// frappe.ui.form.PrintView exists only on the print page, which is the only page this script runs on.
const BasePrintView = frappe.ui.form.PrintView;

if (BasePrintView) {
	// extend the PrintView class to add a menu item to mail the letter
	frappe.ui.form.PrintView = class PrintView extends BasePrintView {
		// No class fields: the base constructor calls make(), and field initialisers would run after it.
		/** @override */
		make() {
			super.make();
			/** @type {PostGridDefaults | undefined} */
			this.postgrid_defaults = undefined;
			this.erpnext_installed = false;
			this.get_postgrid_defaults();
			this.mail_button_added = false;
			void frappe.xcall("frappe.core.doctype.module_def.module_def.get_installed_apps").then((r) => {
				this.erpnext_installed = Array.isArray(r) && r.includes("erpnext");
			});
		}

		get_postgrid_defaults() {
			void frappe.call({
				method: "postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.get_postgrid_defaults",
				/** @param {import("frappe-types").FrappeResponse<PostGridDefaults>} r */
				callback: (r) => {
					this.postgrid_defaults = r.message;
				},
			});
		}

		/**
		 * @override
		 * @param {frappe.ui.form.PrintViewTarget} frm
		 */
		show(frm) {
			const shown = super.show(frm);
			this.add_mail_button(/** @type {PrintedDoc} */ (frm.doc));
			return shown;
		}

		/** @param {PrintedDoc} doc */
		add_mail_button(doc) {
			if (doc.docstatus == 0) return;
			if (!this.mail_button_added) {
				this.page.add_button(__("Mail"), () => this.mail_letter_dialog(doc), { icon: "mail" });
				this.mail_button_added = true;
			}
		}

		/** @param {PrintedDoc} doc */
		mail_letter_dialog(doc) {
			const postgrid_defaults = this.postgrid_defaults;
			/** @param {unknown} value */
			const as_name = (value) => (typeof value === "string" && value ? value : null);
			let default_from_address = as_name(doc["company_address"]);
			const default_to_address =
				as_name(doc["customer_address"]) ??
				as_name(doc["shipping_address"]) ??
				as_name(doc["billing_address"]) ??
				as_name(doc["supplier_address"]) ??
				as_name(doc["address"]);
			const default_to_contact = as_name(doc["contact_person"]);

			// if from address is missing and ERPNext is installed, get the default company address
			if (!default_from_address && this.erpnext_installed) {
				const company =
					as_name(doc["company"]) ??
					as_name(frappe.defaults.get_user_default("Company")) ??
					as_name(frappe.defaults.get_default("Company"));
				if (company) {
					void frappe.call({
						method: "erpnext.setup.doctype.company.company.get_default_company_address",
						args: { name: company },
						debounce: 2000,
						callback(r) {
							default_from_address = as_name(r?.message) ?? "";
						},
					});
				}
			}

			const misc = postgrid_defaults?.misc;
			const d = new frappe.ui.Dialog({
				title: "Mail Letter",
				fields: [
					{
						fieldname: "section_break_1",
						fieldtype: "Section Break",
						hide_border: 1,
					},
					{
						label: "From Address",
						fieldname: "from_address",
						fieldtype: "Link",
						options: "Address",
						default: default_from_address,
						reqd: 1,
					},
					{
						fieldname: "section_break_2",
						fieldtype: "Section Break",
						hide_border: 1,
					},
					{
						label: "To Address",
						fieldname: "to_address",
						fieldtype: "Link",
						options: "Address",
						default: default_to_address,
						reqd: 1,
					},
					{
						fieldname: "column_break_2",
						fieldtype: "Column Break",
					},
					{
						label: "To Contact",
						fieldname: "to_contact",
						fieldtype: "Link",
						options: "Contact",
						default: default_to_contact,
						reqd: 0,
					},
					{
						fieldname: "section_break_3",
						fieldtype: "Section Break",
						hide_border: 1,
					},
					{
						label: "Address Placement",
						fieldname: "address_placement",
						fieldtype: "Select",
						options: [
							{ value: "insert_blank_page", label: "Insert Blank Page" },
							{ value: "top_first_page", label: "Top of First Page" },
						],
						default: postgrid_defaults?.address_placement,
						reqd: 1,
					},
					{
						label: "Additional Options",
						fieldname: "misc",
						fieldtype: "MultiCheck",
						// MultiCheck reads each option's `checked` (form/controls/multicheck.js:112-114).
						// frappe-types' SelectOption has no `checked`, so the options come from
						// get_data, which the control reads in place of `options` (multicheck.js:46-56).
						get_data: () => [
							{ value: "double_sided", label: "Double Sided", checked: misc?.double_sided },
							{ value: "color", label: "Color", checked: misc?.color },
							{ value: "express", label: "Express", checked: misc?.express },
						],
					},
					{
						fieldname: "column_break_3",
						fieldtype: "Column Break",
					},
					{
						label: "Envelope Type",
						fieldname: "envelope_type",
						fieldtype: "Select",
						options: [
							{ value: "standard_double_window", label: "Standard Double Window" },
							{ value: "flat", label: "Flat" },
						],
						default: postgrid_defaults?.envelope_type,
						reqd: 1,
					},
					{
						fieldname: "with_cover_letter",
						fieldtype: "Check",
						label: "With Cover Letter",
					},
					{
						depends_on: "with_cover_letter",
						fieldname: "cl_print_format",
						fieldtype: "Link",
						label: "Cover Letter Print Format",
						mandatory_depends_on: "with_cover_letter",
						options: "Print Format",
						get_query: () => ({
							filters: {
								doc_type: doc.doctype,
							},
						}),
					},
				],
				// "medium" is not one of frappe's sizes. It adds no size class, and because a size is set the
				// dialog doesn't size itself from its column breaks (ui/dialog.js:44-50), which would make
				// this one "large". So it keeps the default width, which frappe-types' DialogSize can't name.
				size: /** @type {import("frappe-types").DialogSize} */ (/** @type {unknown} */ ("medium")),
				primary_action_label: "Mail via PostGrid",
				primary_action: (parameters) => {
					d.hide();
					this.mail_letter(doc, /** @type {MailLetterValues} */ (parameters));
				},
			});
			d.show();
		}

		/**
		 * @param {PrintedDoc} doc
		 * @param {MailLetterValues} parameters
		 */
		mail_letter(doc, parameters) {
			const current_print_format = this.selected_format();

			void frappe.call({
				method: "postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.mail_letter",
				args: {
					doctype: doc.doctype,
					docname: doc.name,
					print_format: current_print_format,
					from_address: parameters.from_address,
					to_address: parameters.to_address,
					to_contact: parameters.to_contact,
					pg_parameters: parameters,
					cl_print_format: parameters.with_cover_letter ? parameters.cl_print_format : null,
				},
				/** @param {import("frappe-types").FrappeResponse<MailLetterResult>} r */
				callback(r) {
					if (r.message) {
						const alert = r.message;
						frappe.show_alert({
							message: alert.message,
							indicator: alert.indicator,
						});
					}
				},
			});
		}
	};
}
