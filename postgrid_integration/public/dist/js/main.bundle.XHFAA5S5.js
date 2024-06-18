(() => {
  // frappe-html:/var/www/erp.avu.nu/html/apps/postgrid_integration/postgrid_integration/public/js/templates/direct_mail_timeline.html
  frappe.templates["direct_mail_timeline"] = `<div class="timeline-message-box" data-communication-type="{{ communication_type }}">
	<span class="flex justify-between m-1 mb-3">
		<span class="text-color flex">
			<span>{{ __("Letter mailed to") }} {{ recipients }}
				<div class="text-muted">{{ comment_when(communication_date || creation) }}</div>
			</span>
		</span>
		<span class="actions" style="flex-shrink: 0">
			{% let indicator_color = "red"; %}
			{% if (["Sent", "Clicked"].includes(delivery_status)) { %}
				{% indicator_color = "green"; %}
			{% } else if (["Sending", "Scheduled"].includes(delivery_status)) { %}
				{% indicator_color = "orange"; %}
			{% } else if (["Opened", "Read"].includes(delivery_status)) { %}
				{% indicator_color = "blue"; %}
			{% } else if (delivery_status == "Error") { %}
				{% indicator_color = "red"; %}
			{% } %}
			<span class="indicator-pill {%= indicator_color %}-indicator">
				{%= delivery_status %}
			</span>
			{% if (message_id) { %}
				<a class="action-btn" href="https://dashboard.postgrid.com/dashboard/letters/{%= message_id %}"
					title="{{ __('Open in PostGrid') }}">
					<svg class="icon icon-sm">
						<use href="#icon-link-url" class="open-icon"></use>
					</svg>
				</a>
			{% } %}
		</span>
	</span>
	<div class="content">
		{{ content }}
	</div>
</div>`;
})();
//# sourceMappingURL=main.bundle.XHFAA5S5.js.map
