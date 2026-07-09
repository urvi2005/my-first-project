import threading
import time

import requests

from odoo import api, fields, models


class ScayleUrl(models.Model):
    _name = "scayle.url"
    _description = "Scayle URL To Forward Payload"
    _rec_name = "url"

    url = fields.Text(
        string="Scayle URL To Forward Payloads",
        help="The format of this field should be "
        "[custom_domain]/api/scayle/v1/order-create/[access_token]",
        required=True,
    )
    scayle_backend_ids = fields.Many2many(
        comodel_name="scayle.backend",
        relation="scayle_backend_scayle_url_rel",
        column1="scayle_url_id",
        column2="scayle_backend_id",
        string="Backends",
        copy=False,
    )
    active = fields.Boolean(default=True)

    @api.model
    def _cron_forward_scayle_sale_order_payload(self):
        scayle_urls = self.with_context(active_test=False).search([])
        if not scayle_urls:
            return
        headers = {
            "Content-Type": "application/json",
        }
        for url in scayle_urls:
            active = False
            attempt_counter = 0
            while attempt_counter < 3:
                try:
                    # pylint: disable=E8106
                    response = requests.post(
                        url.url,
                        headers=headers,
                        json={},
                    )
                    # T-02767 - Added a timeout to handle error where
                    # server takes long to respond.
                except Exception:
                    attempt_counter += 1
                    active = False
                    if (
                        not getattr(threading.current_thread(), "testing", False)
                        or not self.env.registry.in_test_mode()
                    ):
                        time.sleep(5)
                    continue
                if response.status_code == 200:
                    active = True
                    break
                if (
                    not getattr(threading.current_thread(), "testing", False)
                    or not self.env.registry.in_test_mode()
                ):
                    time.sleep(5)

            url.active = active
