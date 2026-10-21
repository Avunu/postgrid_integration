# Development

`nix develop` (or direnv) gives you Node, yarn, the git hooks and a dev bench with the app installed.

| Command                              | What it does                                                                                               |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `yarn check`                         | Checks the formatting, lints and type-checks the desk scripts                                              |
| `yarn lint` / `yarn format`          | Runs oxlint and oxfmt                                                                                      |
| `yarn typecheck`                     | Type-checks the desk scripts (`public/js`, JSDoc-typed) and the screenshot spec                            |
| `yarn lint:py` / `yarn typecheck:py` | Runs ruff and ty on the Python code                                                                        |
| `frappe-test --reuse-site`           | Runs the Python tests on the dev site, with coverage                                                       |
| `frappe-shots`                       | Rebuilds the demo site (`postgrid_direct_mail/demo.py`) and retakes the screenshots in `docs/screenshots/` |

The tests never reach PostGrid: they replace the client's `Letter.create` and `Webhook.create`, and Frappe's PDF rendering, with stand-ins (`postgrid_direct_mail/tests/utils.py`). The demo does the same.

## Where things live

- `postgrid_direct_mail/postgrid_integration/doctype/postgrid_settings/__init__.py`: the whitelisted methods: `mail_letter`, `get_postgrid_defaults`, the `webhooks` endpoint, and the timeline content.
- `postgrid_direct_mail/postgrid_integration/doctype/postgrid_settings/postgrid_settings.py`: the settings DocType, the PostGrid client and webhook registration, and the **Reset Webhooks** action.
- `postgrid_direct_mail/postgrid_integration/hooks/notification.py`: the Notification extension that mails on the **Mailed Letter** channel.
- `postgrid_direct_mail/postgrid_integration/custom/`: the custom fields on Address and Notification.
- `postgrid_direct_mail/install.py`, `postgrid_direct_mail/setup/custom_fields.py`: the install, migrate and uninstall hooks.
- `postgrid_direct_mail/public/js/print_view.js`: the print view's **Mail** button and dialog.
- `postgrid_direct_mail/public/js/notification.js`: the Notification form for the mail channels.
- `postgrid_direct_mail/public/js/templates/direct_mail_timeline.html`: the timeline card.
- `postgrid_direct_mail/demo.py`: the demo data for `frappe-demo` and the screenshots.
- `marketplace/`: the marketplace listing and the screenshot spec.

## The rename

The app was called `postgrid_integration` before. `hooks.py` keeps the old dotted paths of the whitelisted methods working (the block between the `frappe-nix:rename-shim` markers) for callers that still use them, such as webhooks registered before the rename. Keep it for at least one minor release after the rename.
