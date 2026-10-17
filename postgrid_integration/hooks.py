# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

additional_timeline_content = {
	"*": ["postgrid_integration.postgrid_integration.doctype.postgrid_settings.get_timeline_content"],
}
after_install = "postgrid_integration.install.after_install"
after_migrate = "postgrid_integration.install.after_migrate"
app_description = "PostGrid Integration providing direct mail on demand for Frappe Documents"
app_email = "mail@avu.nu"
app_include_js = "main.bundle.js"
app_license = "MIT"
app_name = "postgrid_integration"
app_publisher = "Avunu LLC"
app_title = "PostGrid Integration"
before_uninstall = "postgrid_integration.install.before_uninstall"
doctype_js = {"Notification": "public/js/notification.js"}
page_js = {"print": "public/js/print_view.js"}
scheduler_events = {
	"daily": [
		"postgrid_integration.postgrid_integration.hooks.notification.trigger_daily_direct_mail_notifications"
	]
}
doc_events = {
	"*": {
		"after_insert": "postgrid_integration.postgrid_integration.hooks.notification.run_direct_mail_notifications",
		"on_update": "postgrid_integration.postgrid_integration.hooks.notification.run_direct_mail_notifications",
		"on_submit": "postgrid_integration.postgrid_integration.hooks.notification.run_direct_mail_notifications",
		"on_cancel": "postgrid_integration.postgrid_integration.hooks.notification.run_direct_mail_notifications",
	},
	"Notification": {
		"on_update": "postgrid_integration.postgrid_integration.hooks.notification.direct_mail_notification_update",
	},
}
# ERPNext is optional: the desk scripts use its default company address only when it is installed.
required_apps = []
