from odoo.tests.common import users

from .common import ScayleTestCases


class ScayleStockMoveLinePriceTest(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """#T-03105: Shared setup for stock move line price computation tests."""
        super().setUpClass()

        external_id = cls.scayle_order_payload.get("orderId")
        cls.binding_model.import_record(
            backend=cls.scayle_backend,
            external_id=external_id,
            data=cls.scayle_order_payload,
        )
        sale_binding = cls.binding_model.sudo().search(
            [("external_id", "=", external_id)]
        )
        sale_order = sale_binding.odoo_id
        sale_order.action_confirm()

        picking = sale_order.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        picking.ensure_one()

        cls.first_sale_line = sale_order.order_line[0]
        cls.stock_move_lines = picking.move_line_ids

    def _get_first_move_line(self):
        return self.stock_move_lines.filtered(
            lambda ml: ml.move_id.sale_line_id == self.first_sale_line
        )

    @users("sale_manager")
    def test_01_full_quantity_uniform_prices(self):
        """
        #T-03105: Full qty with uniform binding prices.
        avg × qty should equal the sum of all binding prices.
        """
        first_move_line = self._get_first_move_line()
        self.assertTrue(first_move_line, "Stock move line for sale line should exist")

        first_move_line.quantity = self.first_sale_line.product_uom_qty

        expected = sum(
            self.first_sale_line.scayle_bind_ids.mapped("eshop_price_with_tax")
        )
        self.assertAlmostEqual(
            first_move_line.eshop_price_with_tax,
            expected,
            places=2,
            msg="eshop_price_with_tax should equal sum binding prices at full qty",
        )

    @users("sale_manager")
    def test_02_zero_quantity_gives_zero_price(self):
        """
        #T-03105: qty=0 → eshop_price_with_tax must be 0.
        int(0.0) * avg = 0, so the field should stay at 0.
        """
        first_move_line = self._get_first_move_line()
        self.assertTrue(first_move_line, "Stock move line for sale line should exist")

        first_move_line.quantity = 0.0

        self.assertAlmostEqual(
            first_move_line.eshop_price_with_tax,
            0.0,
            places=2,
            msg="eshop_price_with_tax should be 0 when quantity is 0",
        )

    @users("sale_manager")
    def test_03_different_binding_prices_uses_average(self):
        """
        #T-03105: When binding prices differ, the average must be used —
        not the first/highest ranked price.
        Directly exercises the avg logic that replaced the ranking approach.
        E.g. bindings = [70, 69], qty=2 → avg=69.5 × 2 = 139.0
        """
        first_move_line = self._get_first_move_line()
        self.assertTrue(first_move_line, "Stock move line for sale line should exist")

        bindings = self.first_sale_line.scayle_bind_ids
        # Force distinct prices on the bindings
        prices = [70.0, 69.0]
        bindings[0].eshop_price_with_tax = 70.0
        bindings[1].eshop_price_with_tax = 69.0

        avg_price = (70.0 + 69.0) / 2  # 69.5
        expected = avg_price * int(self.first_sale_line.product_uom_qty)

        first_move_line.quantity = self.first_sale_line.product_uom_qty

        avg_price = sum(prices) / len(prices)  # 69.5
        expected = avg_price * int(self.first_sale_line.product_uom_qty)
        self.assertAlmostEqual(
            first_move_line.eshop_price_with_tax,
            expected,
            places=2,
            msg="eshop_price_with_tax should use average when binding prices differ",
        )
