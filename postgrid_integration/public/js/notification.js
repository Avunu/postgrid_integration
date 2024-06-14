// forcefully enable visibility of the recipient selector when the notification channel is "Mailed Letter"

frappe.ui.form.on('Notification', {
	onload: function(frm) {
		column_break_5_df_property = frm.get_field('column_break_5').df.hidden;
	},
	channel: function(frm) {
		if (frm.doc.channel === 'Mailed Letter') {
			frm.set_df_property('column_break_5', 'hidden', 0);
		} else {
			frm.set_df_property('column_break_5', 'hidden', column_break_5_df_property);
		}
	}
});