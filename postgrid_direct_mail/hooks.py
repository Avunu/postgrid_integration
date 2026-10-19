# Copyright (c) 2026, Avunu LLC and contributors
# For license information, please see license.txt

additional_timeline_content = {
	"*": ["postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.get_timeline_content"],
}
after_install = "postgrid_direct_mail.install.after_install"
after_migrate = "postgrid_direct_mail.install.after_migrate"
# frappe syncs custom/*.json after after_install, so a new site's fields are flagged here
after_sync = "postgrid_direct_mail.install.after_sync"
app_description = "Direct mail on demand for Frappe documents via PostGrid"
app_email = "mail@avu.nu"
app_include_js = "main.bundle.js"
app_license = "MIT"
app_name = "postgrid_direct_mail"
app_publisher = "Avunu LLC"
app_title = "Direct Mail via PostGrid"
before_uninstall = "postgrid_direct_mail.install.before_uninstall"
doctype_js = {"Notification": "public/js/notification.js"}
# Mailed Letter notifications ride on frappe's own notification run, which already covers every DocType
# and the daily events, so the app needs no doc_events["*"] or scheduler job of its own.
extend_doctype_class = {
	"Notification": ["postgrid_direct_mail.postgrid_integration.hooks.notification.DirectMailNotification"],
}
page_js = {"print": "public/js/print_view.js"}
# ERPNext is optional: the desk scripts use its default company address only when it is installed.
required_apps = []


# frappe-nix:rename-shim-begin postgrid_integration
# postgrid_integration's whitelisted methods under their old dotted paths, for callers that still use
# them (cached bundles, webhooks, bookmarks). Written by frappe-rename-app; keep it for
# at least one minor release after the rename.
override_whitelisted_methods = {
	**globals().get("override_whitelisted_methods", {}),
	"postgrid_integration.postgrid_integration.doctype.postgrid_settings.webhooks": "postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.webhooks",
	"postgrid_integration.postgrid_integration.doctype.postgrid_settings.get_postgrid_defaults": "postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.get_postgrid_defaults",
	"postgrid_integration.postgrid_integration.doctype.postgrid_settings.mail_letter": "postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.mail_letter",
	"postgrid_integration.postgrid_integration.doctype.postgrid_settings.postgrid_settings.reset_webhooks": "postgrid_direct_mail.postgrid_integration.doctype.postgrid_settings.postgrid_settings.reset_webhooks",
}
# frappe-nix:rename-shim-end
