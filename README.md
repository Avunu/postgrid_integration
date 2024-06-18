# PostGrid Direct Mail App for Frappe/ERPNext

The PostGrid Direct Mail App is a powerful integration that enables you to send physical letters directly from your Frappe/ERPNext system using [PostGrid's direct mail service](https://www.postgrid.com/ref/avunu). With this app, you can automate your direct mail campaigns, send personalized letters to your customers, and track the delivery status of each letter.

## Features

- Send physical letters directly from Frappe/ERPNext
- Automate direct mail campaigns
- Personalize letters with recipient information
- Track delivery status of each letter
- View letter history and details within Frappe/ERPNext
- Seamless integration with PostGrid's direct mail service

## Installation

```
bench get-app avunu/postgrid_integration
bench --site [site-name] install-app postgrid_integration
```

## Configuration

1. [Set up your PostGrid account](https://www.postgrid.com/ref/avunu) and [obtain the API credentials](https://dashboard.postgrid.com/dashboard/settings).
2. In Frappe/ERPNext, go to the PostGrid Settings.
3. Enter your PostGrid API credentials in the designated fields.
4. Customize the PostGrid options to your liking.
5. Save the configuration.
