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
# Mailed Letter notifications ride on frappe's own notification run, which already covers every DocType
# and the daily events, so the app needs no doc_events["*"] or scheduler job of its own.
extend_doctype_class = {
	"Notification": ["postgrid_integration.postgrid_integration.hooks.notification.DirectMailNotification"],
}
page_js = {"print": "public/js/print_view.js"}
# ERPNext is optional: the desk scripts use its default company address only when it is installed.
required_apps = []
