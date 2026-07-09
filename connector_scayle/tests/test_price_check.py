from odoo.tests.common import users

from odoo.addons.connector_scayle.tests.common import ScayleTestCases


class ScaylePriceCheck(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Configurations for Sale Order #T-02515"""
        super().setUpClass()
        cls.cost_dict = {
            "costCapture": 97690,
            "tax": {"vat": {"amount": 18267}},
            "withTax": 97690,
            "withTaxWithMembershipDiscountWithoutServiceCosts": 97690,
            "withoutTax": 79423,
            "withoutTaxWithMembershipDiscount": 79423,
            "appliedFees": [
                {
                    "category": "delivery",
                    "key": "at_post_at_standard",
                    "option": "deliveryCosts",
                    "tax": {"vat": {"amount": 6732, "rate": 23}},
                    "amount": {"withoutTax": 29268, "withTax": 36000},
                }
            ],
        }
        cls.scayle_order_product_1 = cls.env.ref("connector_scayle.demo_product_1")
        cls.scayle_order_product_1.write({"taxes_id": cls.tax_23})
        cls.scayle_order_product_2 = cls.env.ref("connector_scayle.demo_product_2")
        cls.scayle_order_product_2.write({"taxes_id": cls.tax_23})
        # Commented code for future reference. # T-02556
        # This product is for shipping line product
        # self.scayle_order_product_3 = self.env.ref("connector_scayle.demo_product_3")

        cls.scayle_order_payload.update({"cost": cls.cost_dict})
        cls.external_id = cls.scayle_order_payload.get("orderId")

    @users("sale_manager")
    def test_01_price(self):
        """New Method: Added test cases to calculate prices. #T-02515"""
        # T-02857 check current user as sales manager.
        self.assertEqual(
            self.env.user,
            self.sale_manager,
            "Current User is not the Sales Manager",
        )
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.external_id,
            data=self.scayle_order_payload,
        )
        self.sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id)]
        )
        # Commented code for future reference. # T-02556
        # Test Cases to check for creation of shipping line. # T-02556
        # self.assertEqual(
        #     len(self.sale_binding.odoo_id.order_line),
        #     3,
        #     "Shipping line should be added!!",
        # )
        # 1 Line product_name is Test1
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[0]
            .scayle_bind_ids[0]
            .eshop_price_with_tax,
            99.0,
            "Price With Tax does not match.",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[0]
            .scayle_bind_ids[0]
            .eshop_price_without_tax,
            80.49,
            "Price Without Tax does not match.",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[0].product_id.id,
            self.scayle_order_product_1.id,
            "Product Does not match!",
        )
        # 1 Line product_name is Test1
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[0].price_unit,
            self.scayle_order_product_1.lst_price,
            "Unit Price of Sale Order Line is not appropriate.",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[0].product_uom_qty,
            2,
            "Qty of product does not match.",
        )
        self.assertIn(
            self.tax_23.id,
            self.sale_binding.odoo_id.order_line[0].tax_id.ids,
            "Tax of product does not match.",
        )
        self.assertEqual(
            len(self.sale_binding.odoo_id.order_line[0].tax_id.ids),
            1,
            "More than one tax Added.",
        )
        # 2 Line product_name is Test2
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[1].price_unit,
            self.scayle_order_product_2.lst_price,
            "Unit Price of Sale Order Line is not appropriate.",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[1].product_id.id,
            self.scayle_order_product_2.id,
            "Product Does not match!",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[1].product_uom_qty,
            1,
            "Qty of product does not match.",
        )
        self.assertEqual(
            float(
                "{:.2f}".format(
                    self.sale_binding.odoo_id.order_line[1]
                    .scayle_bind_ids[0]
                    .eshop_price_with_tax
                )
            ),
            418.9,
            "Price With Tax does not match.",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.order_line[1]
            .scayle_bind_ids[0]
            .eshop_price_without_tax,
            340.57,
            "Price Without Tax does not match.",
        )
        self.assertEqual(
            len(self.sale_binding.odoo_id.order_line[1].tax_id.ids),
            1,
            "More than one tax Added.",
        )
        self.assertIn(
            self.tax_23.id,
            self.sale_binding.odoo_id.order_line[1].tax_id.ids,
            "Tax of product does not match.",
        )
        # 3 Line (Shipping line)
        self.assertEqual(
            self.sale_binding.odoo_id.eshop_shipping_without_tax_price,
            292.68,
            "Price Without Tax does not match.",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.eshop_shipping_with_tax_price,
            360.0,
            "Price With Tax does not match.",
        )
        self.assertEqual(
            float(f"{self.sale_binding.odoo_id.eshop_shipping_tax_amount:.2f}"),
            67.32,
            "Shipping Tax Amount does not match.",
        )
        self.assertEqual(
            self.sale_binding.odoo_id.eshop_shipping_tax_rate,
            23.0,
            "Shipping Tax Rate does not match.",
        )
        # Commented code for future reference. # T-02556
        # Test cases to check for shipping line. # T-02556
        # self.assertEqual(
        #     self.sale_binding.odoo_id.order_line[2].price_unit,
        #     self.scayle_order_product_3.lst_price,
        #     "Unit Price of Shipping line is not appropriate.",
        # )
        # self.assertEqual(
        #     self.sale_binding.odoo_id.order_line[2].product_id.id,
        #     self.scayle_order_product_3.id,
        #     "Product Does not match!",
        # )
        # self.assertEqual(
        #     self.sale_binding.odoo_id.order_line[2].product_uom_qty,
        #     1,
        #     "Qty of product does not match.",
        # )
        # self.assertEqual(
        #     len(self.sale_binding.odoo_id.order_line[2].tax_id.ids),
        #     1,
        #     "More than one tax Added.",
        # )
        # self.assertIn(
        #     self.tax_23.id,
        #     self.sale_binding.odoo_id.order_line[2].tax_id.ids,
        #     "Tax of product does not match.",
        # )
