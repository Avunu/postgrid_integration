# PostGrid Direct Mail App for Frappe/ERPNext

The PostGrid Direct Mail App is a powerful integration that enables you to send physical letters directly from your Frappe/ERPNext system using [PostGrid's Print & Mail API](https://www.postgrid.com/ref/avunu). With this app, you can mail the printed version of any document, such as invoices, purchase orders, or customer statements, to your Frappe contacts, such as customers, vendors, and employees. Furthermore, you can automate direct mail campaigns using the additional capabilties added to core Notifications.

## Features

- Send physical letters directly from Frappe/ERPNext
- Automate direct mail campaigns
- Personalize letters with recipient information
- Track delivery status of each letter
- View letter history and details within Frappe/ERPNext
- Seamless integration with PostGrid's direct mail service

## Demo

From the print format of any document, you can send a physical letter to any recipient using the added "Mail" option:
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
3. Enter your PostGrid API credentials in the designated fields.
4. Customize the PostGrid options to your liking.
5. Save the configuration.
