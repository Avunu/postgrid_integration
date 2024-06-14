// extend the PrintView class to add a menu item to mail the letter
frappe.ui.form.PrintView = class PrintView extends frappe.ui.form.PrintView {
    make() {
        super.make();
        this.get_postgrid_defaults();
        this.mail_button_added = false;
    }

    get_postgrid_defaults() {
        frappe.call({
            method: 'postgrid_integration.postgrid_integration.doctype.postgrid_settings.get_postgrid_defaults',
            callback: (r) => {
                this.postgrid_defaults = r.message;
            }
        });
    }

    show(frm) {
        super.show(frm);
        this.add_mail_button(frm.doc);
    }

    add_mail_button(doc) {
        if (doc.docstatus == 0) return;
        if (!this.mail_button_added) {
            this.page.add_button(__("Mail"), () => this.mail_letter_dialog(doc), { icon: "mail" });
            this.mail_button_added = true;
        }
    }

    mail_letter_dialog(doc) {
        let postgrid_defaults = this.postgrid_defaults;
        let default_from_address = doc.company_address || null;
        let default_to_address = doc.customer_address || doc.shipping_address || doc.billing_address || doc.supplier_address || doc.address || null;
        let default_to_contact = doc.contact_person || null;

        if (!default_from_address && doc.company) {
            frappe.call({
                method: "erpnext.setup.doctype.company.company.get_default_company_address",
                args: { name: doc.company, existing_address: doc.company_address || "" },
                debounce: 2000,
                callback: function (r) {
                    default_from_address = (r && r.message) || "";
                },
            });
        }

        let d = new frappe.ui.Dialog({
            title: 'Mail Letter',
            fields: [
                {
                    fieldname: 'section_break_1',
                    fieldtype: 'Section Break',
                    hide_border: 1
                },
                {
                    label: 'From Address',
                    fieldname: 'from_address',
                    fieldtype: 'Link',
                    options: 'Address',
                    default: default_from_address,
                    reqd: 1
                },
                {
                    fieldname: 'section_break_2',
                    fieldtype: 'Section Break',
                    hide_border: 1
                },
                {
                    label: 'To Address',
                    fieldname: 'to_address',
                    fieldtype: 'Link',
                    options: 'Address',
                    default: default_to_address,
                    reqd: 1
                },
                {
                    fieldname: 'column_break_2',
                    fieldtype: 'Column Break',
                },
                {
                    label: 'To Contact',
                    fieldname: 'to_contact',
                    fieldtype: 'Link',
                    options: 'Contact',
                    default: default_to_contact,
                    reqd: 0
                },
                {
                    fieldname: 'section_break_3',
                    fieldtype: 'Section Break',
                    hide_border: 1
                },
                {
                    label: 'Address Placement',
                    fieldname: 'address_placement',
                    fieldtype: 'Select',
                    options: [
                        { value: 'insert_blank_page', label: 'Insert Blank Page' },
                        { value: 'top_first_page ', label: 'Top of First Page' }
                    ],
                    default: postgrid_defaults.address_placement,
                    reqd: 1
                },
                {
                    fieldname: 'column_break_3',
                    fieldtype: 'Column Break',
                },
                {
                    label: 'Envelope Type',
                    fieldname: 'envelope_type',
                    fieldtype: 'Select',
                    options: [
                        { value: 'standard_double_window', label: 'Standard Double Window' },
                        { value: 'flat', label: 'Flat' }
                    ],
                    default: postgrid_defaults.envelope_type,
                    reqd: 1
                },
                {
                    fieldname: 'section_break_4',
                    fieldtype: 'Section Break',
                    hide_border: 1
                },
                {
                    label: 'Additional Options',
                    fieldname: 'misc',
                    fieldtype: 'MultiCheck',
                    options: [
                        { value: 'double_sided', label: 'Double Sided', checked: postgrid_defaults.misc.double_sided },
                        { value: 'color', label: 'Color', checked: postgrid_defaults.misc.color },
                        { value: 'express', label: 'Express', checked: postgrid_defaults.misc.express },
                    ],
                },
            ],
            size: 'medium',
            primary_action_label: 'Mail via PostGrid',
            primary_action: (parameters) => {
                d.hide();
                this.mail_letter(doc, parameters);
            }
        });
        d.show();
    }

    mail_letter(doc, parameters) {
        let currentPrintFormat = this.print_format_selector.val();

        frappe.call({
            method: 'postgrid_integration.postgrid_integration.doctype.postgrid_settings.mail_letter',
            args: {
                doctype: doc.doctype,
                docname: doc.name,
                print_format: currentPrintFormat,
                parameters: parameters,
            },
            callback: function (r) {
                if (r.message) {
                    const alert = r.message;
                    frappe.show_alert({
                        message: alert.message,
                        indicator: alert.indicator,
                    });
                }
            }
        });
    }
}