// Copyright (c) 2026, Avunu LLC and contributors
// For license information, please see license.txt

import type { ShotSpec } from "./shots.d.ts";

// The demo from postgrid_direct_mail/demo.py: submitted Customer Statements, two of them mailed.
const UNMAILED = "/app/print/Customer%20Statement/STMT-0003";
const MAILED = "/app/customer-statement/STMT-0002";
const MAIL_BUTTON = '.custom-actions [data-label="Mail"]';
const DIALOG = ".modal.show";

export default {
	demo: { date: "2026-01-15", seed: 1 },
	shots: [
		{
			name: "mail-dialog",
			route: UNMAILED,
			alt: "The Mail Letter dialog on a statement's print view, with the sender, recipient, contact and mailing options filled in",
			waitFor: MAIL_BUTTON,
			actions: [
				{ waitFor: ".print-format-container, .print-preview" },
				{ click: MAIL_BUTTON },
				{ waitFor: `${DIALOG} [data-fieldname="to_contact"] input` },
				{ wait: 1000 },
			],
			readme: "hero",
			featured: true,
		},
		{
			name: "timeline",
			route: MAILED,
			alt: "A mailed letter in the statement's timeline, with its recipient, delivery status and PostGrid menu",
			waitFor: '.timeline-message-box[data-communication-type="Mailed Letter"]',
			actions: [
				{
					eval: 'document.querySelector(\'.timeline-message-box[data-communication-type="Mailed Letter"]\').scrollIntoView({ block: "center" });',
				},
				{ wait: 500 },
			],
			mask: [".frappe-timestamp"],
			readme: "feature",
			featured: true,
		},
		{
			name: "notification",
			route: "/app/notification/Mail%20Statements%20on%20Submit",
			alt: "A Notification on the Mailed Letter channel, with its sender, recipient fields and mailing options",
			waitFor: '[data-fieldname="to_address_document_field"]',
			actions: [
				{
					eval: 'document.querySelector(\'[data-fieldname="section_direct_mail"]\').scrollIntoView({ block: "start" });',
				},
				{ wait: 500 },
			],
			mask: [".frappe-timestamp"],
			readme: "feature",
			featured: true,
		},
		{
			name: "settings",
			route: "/app/postgrid-settings",
			alt: "PostGrid Settings in Test mode, with the default mailing options",
			waitFor: '[data-fieldname="envelope_type"]',
			mask: [".frappe-timestamp"],
			readme: "feature",
		},
	],
} satisfies ShotSpec;
