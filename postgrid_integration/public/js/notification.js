const COMMUNICATION_TYPES = [
    "Mailed Letter",
    "Postcard",
    "Cheque"
]

frappe.ui.form.on('Notification', {
    onload: function(frm) {
        column_break_5_df_property = frm.get_field('column_break_5').df.hidden;

        // Store the original setup_fieldname_select function
        frappe.notification.original_setup_fieldname_select = frappe.notification.setup_fieldname_select;

        // Override the setup_fieldname_select function
        frappe.notification.setup_fieldname_select = function(frm) {
            // Define the get_select_options function
            let get_select_options = function(df, parent_field) {
                // Append parent_field name along with fieldname for child table fields
                let select_value = parent_field ? df.fieldname + "," + parent_field : df.fieldname;

                return {
                    value: select_value,
                    label: df.fieldname + " (" + __(df.label, null, df.parent) + ")",
                };
            };
            // Call the original setup_fieldname_select function
            frappe.notification.original_setup_fieldname_select(frm);

            // Check if the selected channel is in the COMMUNICATION_TYPES list
            if (frm.doc.document_type && COMMUNICATION_TYPES.includes(frm.doc.channel)) {
                frappe.model.with_doctype(frm.doc.document_type, function() {
                    let fields = frappe.get_meta(frm.doc.document_type).fields;
                    let address_fields = $.map(fields, function(d) {
                        return d.options == "Address" && d.fieldtype == "Link" ? get_select_options(d) : null;
                    });

                    // Update the receiver_by_document_field options
                    frm.fields_dict.recipients.grid.update_docfield_property(
                        "receiver_by_document_field",
                        "options",
                        [""].concat(address_fields)
                    );
                });
            }
        };
    },
    channel: function(frm) {
        if (COMMUNICATION_TYPES.includes(frm.doc.channel)) {
            frm.set_df_property('column_break_5', 'hidden', 0);
        } else {
            frm.set_df_property('column_break_5', 'hidden', column_break_5_df_property);
        }

        // Call the modified setup_fieldname_select function
        frappe.notification.setup_fieldname_select(frm);
    },
	document_type: function(frm) {
		// Call the modified setup_fieldname_select function
		frappe.notification.setup_fieldname_select(frm);
	}
});