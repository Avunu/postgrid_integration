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

        // function to populate the to_address_document_field options
        frappe.notification.setup_mailing_document_field_select = function (frm) {
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
    },
    channel: function (frm) {
        if (MAIL_TYPES.includes(frm.doc.channel)) {
            frm.set_df_property("column_break_5", "hidden", 1);
            frm.set_df_property("message_sb", "hidden", 1);
        } else {
            frm.set_df_property("message_sb", "hidden", 0);
            frm.set_df_property("column_break_5", "hidden", 0);
        }

        // Call the modified setup_fieldname_select function
        frappe.notification.setup_mailing_document_field_select(frm);
    },
    document_type: function (frm) {
        // Call the modified setup_fieldname_select function
        frappe.notification.setup_mailing_document_field_select(frm);
    }
});