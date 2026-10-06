# PostGrid Direct Mail App for Frappe/ERPNext

The PostGrid Direct Mail App is a powerful integration that enables you to send physical letters directly from your Frappe/ERPNext system using [PostGrid's Print & Mail API](https://www.postgrid.com/ref/avunu). With this app, you can mail the printed version of a submitted document, such as an invoice, purchase order, or customer statement, to any Frappe Address (optionally addressed to a Contact), such as those of customers, vendors, and employees. Furthermore, you can automate direct mail campaigns using the additional capabilities added to core Notifications.

## Features

- Send physical letters directly from Frappe/ERPNext
- Automate direct mail campaigns
- Choose a print format (and an optional cover letter) for each mailing
- Track delivery status of each letter through PostGrid webhooks
- View letter history and details in the document timeline, with an optional saved PDF copy
- Seamless integration with PostGrid's direct mail service

## Demo

From the print view of a submitted document, you can send a physical letter to any recipient using the added "Mail" button:
![PostGrid Mailing](https://github.com/Avunu/postgrid_integration/assets/4996285/58ed1243-c0fe-4bef-9280-665d82e2ecf8)

You can also automate your mailings on doctype events using Notifications:
![PostGrid Notification](https://github.com/Avunu/postgrid_integration/assets/4996285/f6988376-aec3-4731-9ad5-eb249827d389)

## Installation

```
bench get-app avunu/postgrid_integration
bench --site [site-name] install-app postgrid_integration
```

## Configuration

1. [Set up your PostGrid account](https://www.postgrid.com/ref/avunu) and [obtain the API credentials](https://dashboard.postgrid.com/dashboard/settings).
2. In Frappe/ERPNext, open the PostGrid Settings.
3. Enter your PostGrid Test and Live API keys, and choose which Mode (Test or Live) is active.
4. Set the default options (address placement, envelope type, double sided, color, express), and choose whether to save PDF copies and update addresses from PostGrid's verified results.
5. Save the configuration. The first save in each mode registers a PostGrid webhook for that mode, so your site must be reachable from the internet for delivery status updates to arrive.

## Current limitations

- Only letters are supported. Postcards and cheques are not implemented yet.

## License

MIT. See [license.txt](license.txt).
