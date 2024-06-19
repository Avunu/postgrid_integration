const MAIL_TYPES = [
    "Mailed Letter",
    "Postcard",
    "Cheque"
]

frappe.ui.form.on("Notification", {
    onload: function (frm) {
        // if channel is already set, trigger the channel event
        if (frm.doc.channel) {
            frm.trigger("channel");
        }
    },
    channel: function (frm) {
        if (MAIL_TYPES.includes(frm.doc.channel)) {
            // hide the fields that are not required for mailed notifications
            frm.set_df_property("column_break_5", "hidden", 1);
            frm.set_df_property("message_sb", "hidden", 1);
            if (frm.fields_dict.column_break_25.is_collapsed()) {
                frm.fields_dict.column_break_25.collapse();
            }
            frm.set_value("attach_print", 1);
            frm.set_df_property("attach_print", "hidden", 1);
            frm.set_df_property("print_format", "hidden", 0);
            // if from address is missing and ERPNext is installed, get the default company address
            if (!frm.doc.from_address) {
                let company = frappe.defaults.get_user_default("Company");
                // exit if company is not set
                if (company) {
                    frappe.call({
                        method: "erpnext.setup.doctype.company.company.get_default_company_address",
                        args: { name: company },
                        debounce: 2000,
                        callback: function (r) {
                            frm.set_value("from_address", (r && r.message) || "");
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
    document_type: function (frm) {
        // populate the to_address_document_field options
        setup_mailing_document_field_select(frm);
        // set the query on the cl_print_format field
        if (frm.doc.document_type) {
            frm.set_query("cl_print_format", function () {
                return {
                    filters: {
                        doc_type: frm.doc.document_type
                    },
                };
            });
        }
    }
});



// function to populate the to_address_document_field options
function setup_mailing_document_field_select(frm) {
    // Define the get_select_options function
    let get_select_options = function (df, parent_field) {
        // Append parent_field name along with fieldname for child table fields
        let select_value = parent_field ? df.fieldname + "," + parent_field : df.fieldname;

        return {
            value: select_value,
            label: df.fieldname + " (" + __(df.label, null, df.parent) + ")",
        };
    };

    // Check if the selected channel is in the MAIL_TYPES list
    if (frm.doc.document_type && MAIL_TYPES.includes(frm.doc.channel)) {
        frappe.model.with_doctype(frm.doc.document_type, function () {
            let fields = frappe.get_meta(frm.doc.document_type).fields;
            let address_fields = $.map(fields, function (d) {
                return d.options == "Address" && d.fieldtype == "Link" ? get_select_options(d) : null;
            });
            let contact_fields = $.map(fields, function (d) {
                return d.options == "Contact" && d.fieldtype == "Link" ? get_select_options(d) : null;
            });

            // Update the receiver_by_document_field options
            frm.set_df_property(
                "to_address_document_field",
                "options",
                [""].concat(address_fields)
            );
            frm.set_df_property(
                "to_contact_document_field",
                "options",
                [""].concat(contact_fields)
            );
        });
    }
};