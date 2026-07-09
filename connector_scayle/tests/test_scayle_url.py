from odoo.tests.common import users

from .common import ScayleTestCases, recorder


class TestScayleUrl(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Configurations for scayle URL. # T-02660"""
        super().setUpClass()

    @users("connector_sale_inventory_manager")
    def test_forward_scayle_sale_order(self):
        """New Method: Added test cases for forward payload. # T-02660"""
        self.env["scayle.url"].create(
            [
                {
                    "url": "http://localhost/api/scayle/v1/order-create/123123123",
                    "scayle_backend_ids": [(6, 0, self.scayle_backend.ids)],
                },
                # Added URL for generating error. # T-02660
                {
                    "url": "http://localhost/api/scayle/v1/order-create/456456",
                    "scayle_backend_ids": [(6, 0, self.scayle_backend.ids)],
                },
            ]
        )
        with recorder.use_cassette("forward_scayle_sale_order"):
            self.env["scayle.url"]._cron_forward_scayle_sale_order_payload()
        data = {"name": "test"}
        response = self.scayle_backend.forward_data_to_scayle_url(
            url="http://localhost/api/scayle/v1/order-create/123123123", data={}
        )
        self.assertFalse(response, "There is no data so should return null")
        with recorder.use_cassette("forward_scayle_sale_order"):
            self.scayle_backend.forward_data_to_scayle_url(
                url="http://localhost/api/scayle/v1/order-create/123123123", data=data
            )

    @users("connector_sale_inventory_manager")
    def test_no_scayle_urls(self):
        """New Method: Added test cases for no URLs. # T-02660"""
        with recorder.use_cassette("forward_scayle_sale_order"):
            response = self.env["scayle.url"]._cron_forward_scayle_sale_order_payload()
        self.assertFalse(response, "There is no scayle url so should return null")
