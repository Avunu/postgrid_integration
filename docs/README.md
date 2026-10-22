# Direct Mail via PostGrid

Direct mail for Frappe: send documents as physical letters via PostGrid

Direct Mail via PostGrid is a Frappe app that mails the printed version of a Frappe or ERPNext document as a physical letter through [PostGrid's Print & Mail API](https://www.postgrid.com/ref/avunu). You can mail a submitted document, such as an invoice, purchase order or customer statement, to any Frappe Address (optionally addressed to a Contact), such as those of customers, suppliers and employees. You can also automate direct mail with the Mailed Letter channel it adds to Notifications.

## Features

- Send physical letters from the print view of any submitted document
- Mail documents automatically from Notifications
- Choose a print format (and an optional cover letter) for each mailing
- Track the delivery status of each letter through PostGrid webhooks
- See each letter in the document timeline, with an optional saved PDF copy

## Demo

From the print view of a submitted document, you can send a physical letter to any recipient using the added "Mail" button:
![PostGrid Mailing](https://github.com/Avunu/postgrid_direct_mail/assets/4996285/58ed1243-c0fe-4bef-9280-665d82e2ecf8)

You can also automate your mailings on doctype events using Notifications:
![PostGrid Notification](https://github.com/Avunu/postgrid_direct_mail/assets/4996285/f6988376-aec3-4731-9ad5-eb249827d389)

## Installation

```
bench get-app https://github.com/Avunu/postgrid_direct_mail --branch develop
bench --site [site-name] install-app postgrid_direct_mail
```

## Configuration

1. [Set up your PostGrid account](https://www.postgrid.com/ref/avunu) and [obtain the API credentials](https://dashboard.postgrid.com/dashboard/settings).
2. In Frappe/ERPNext, open the PostGrid Settings.
3. Enter your PostGrid Test and Live API keys, and choose which Mode (Test or Live) is active.
4. Set the default options (address placement, envelope type, double sided, color, express), and choose whether to save PDF copies and update addresses from PostGrid's verified results.
5. Save the configuration. The first save in each mode registers a PostGrid webhook for that mode, so your site must be reachable from the internet for delivery status updates to arrive.

## Current limitations

- Only letters are supported. Postcards and cheques are not implemented yet.
- A Mailed Letter notification mails on the New, Save, Submit, Cancel, Days Before and Days After events, and on a Method event for `after_insert`, `on_update`, `on_submit` or `on_cancel`. The Value Change, Minutes Before and Minutes After events don't mail.
- A notification's To Contact Field has no effect yet: the letter is addressed without the contact's name. Letters sent from the print view do include the contact.
- Without ERPNext, when a document has no company address, the Mail dialog's From Address starts empty and has to be picked by hand.

## Development

The commands, the source layout and the rename shim are described in [Development](development.md).

## License

[MIT](https://github.com/Avunu/postgrid_direct_mail/blob/develop/license.txt), Copyright (c) 2024–present Avunu LLC.
