additional_timeline_content = {
    "*": ["postgrid_integration.postgrid_integration.doctype.postgrid_settings.get_timeline_content"],
}
after_install = "postgrid_integration.config.after_install"
after_migrate = "postgrid_integration.config.after_migrate"
after_uninstall = "postgrid_integration.config.after_uninstall"
app_description = (
    "PostGrid Integration providing direct mail on demand for Frappe Documents"
)
app_email = "mail@avu.nu"
app_include_js = "main.bundle.js"
app_license = "mit"
app_name = "postgrid_integration"
app_publisher = "Avunu LLC"
app_title = "PostGrid Integration"
doctype_js = {"Notification": "public/js/notification.js"}
page_js = {"print": "public/js/print_view.js"}
scheduler_events = {
    "daily": [
        "postgrid_integration.postgrid_integration.hooks.notification.trigger_daily_mailed_letter_notifications"
    ]
}
doc_events = {
    "*": {
        "after_insert": "postgrid_integration.postgrid_integration.hooks.notification.run_mailed_notifications",
        "on_update": "postgrid_integration.postgrid_integration.hooks.notification.run_mailed_notifications",
        "on_submit": "postgrid_integration.postgrid_integration.hooks.notification.run_mailed_notifications",
        "on_cancel": "postgrid_integration.postgrid_integration.hooks.notification.run_mailed_notifications",
    }
}