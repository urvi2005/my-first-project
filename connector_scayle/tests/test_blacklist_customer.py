from odoo.tests.common import users

from .common import ScayleTestCases


class ScayleBlacklist(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Configurations for Blacklist Sale Order #T-02935"""
        super().setUpClass()
        # T-02935 Created Blacklist Filters
        BlacklistFilter = cls.env["blacklist.customer.filter"]
        cls.blacklist_filter_1 = BlacklistFilter.create(
            {
                "name": "Name",
                "domain": "[('name', 'ilike', 'Eva')]",
            }
        )
        cls.blacklist_filter_2 = BlacklistFilter.create(
            {
                "name": "ZIP",
                "domain": "[('zip', '=', '602 00')]",
            }
        )

    def get_scayle_sale_orders(self):
        """T-02935 New Method to return normal and blacklisted sale order"""
        so_external_id = self.scayle_order_payload.get("orderId")
        self.scayle_backend.auto_confirm_order = True
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=so_external_id,
            data=self.scayle_order_payload,
        )
        self.sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", so_external_id)]
        )
        scayle_normal_so = self.sale_binding.odoo_id
        external_id = self.scayle_cz_order_payload.get("orderId")
        self.binding_model.import_record(
            backend=self.cz_scayle_backend,
            external_id=external_id,
            data=self.scayle_cz_order_payload,
        )
        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", external_id)]
        )
        # T-02935 Get Sale order
        blacklisted_sale_order = sale_binding.odoo_id
        return scayle_normal_so, blacklisted_sale_order

    @users("sale_manager")
    def test_check_reservation(self):
        """T-02935 New Test Method For Scayle orders"""
        scayle_normal_so, blacklisted_sale_order = self.get_scayle_sale_orders()
        # T-02935 Check state and boolean for normal sale order
        self.assertEqual(
            scayle_normal_so.state,
            "sale",
            "Normal Scayle Sale order should be confirmed",
        )
        self.assertFalse(
            scayle_normal_so.is_blacklisted, "SO Should not be Blacklisted"
        )
        self.assertFalse(
            scayle_normal_so.mapped("order_line.reservation_ids"),
            "Normal Scayle Order Should not have stock reservations",
        )
        # T-02935 Check state, boolean and stock reservation
        self.assertEqual(
            blacklisted_sale_order.state,
            "draft",
            "Blacklisted Scayle Sale order should be in draft",
        )
        self.assertTrue(
            blacklisted_sale_order.is_blacklisted,
            "Blacklisted Sale Order should be Blacklisted",
        )
        # T-02935 Check reservations on sale order line
        for line in blacklisted_sale_order.order_line:
            self.assertTrue(
                line.reservation_ids,
                "Sale Order Line should have at least one reservation.",
            )
            # T-02935 Determine expected product for reservation
            expected_product = line.frame_product_id or line.product_id
            for reservation in line.reservation_ids:
                self.assertEqual(
                    reservation.product_id.id,
                    expected_product.id,
                    "Reservation product and Expected product doesn't match!",
                )
        # T-02935 Process blacklisted sale order
        blacklisted_sale_order.process_order()
        self.assertFalse(
            blacklisted_sale_order.mapped("order_line.reservation_ids"),
            "Blacklisted Scayle Order's stock reservations Should be removed",
        )
