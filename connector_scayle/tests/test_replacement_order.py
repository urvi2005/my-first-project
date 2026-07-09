from odoo.exceptions import ValidationError
from odoo.tests.common import users

from .common import ScayleTestCases


class ReplacementOrderTest(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for replacement order tests."""
        super().setUpClass()
        company = cls.env.company
        cls.scrap_location = cls.env["stock.location"].search(
            [("scrap_location", "=", True), ("company_id", "=", company.id)],
            limit=1,
        )

    def _get_sale_order_with_2_lines(self):
        """Import or fetch a Scayle sale order with 2 lines."""
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
        return self.sale_binding.odoo_id

    def _create_replacement_wizard(
        self, sale_order, line, quantity, reason="Damaged Item"
    ):
        """Create a replacement order wizard for a given sale order line."""
        return self.env["replacement.order"].create(
            {
                "sale_order_id": sale_order.id,
                "replacement_reason": reason,
                "replacement_order_line_ids": [
                    (
                        0,
                        0,
                        {
                            "sale_order_line_id": line.id,
                            "product_id": line.product_id.id,
                            "quantity": quantity,
                        },
                    ),
                ],
            }
        )

    @users("sale_manager")
    def test_replacement_order(self):
        """#T-02873: Test replacement order creation after delivery validation."""
        sale_order = self._get_sale_order_with_2_lines()
        sale_order.picking_ids.button_validate()
        first_sol = sale_order.order_line[0]

        wizard = self._create_replacement_wizard(sale_order, first_sol, 1)
        wizard.action_confirm_replacement()
        self.assertEqual(
            first_sol.replaced_qty,
            1,
            "Replaced quantity should be updated to 1 after replacement confirmation",
        )
        self.assertEqual(
            first_sol.product_uom_qty,
            3,
            "Product UOM quantity should increase after replacement",
        )
        replacement_pickings = sale_order._get_replacement_pickings()
        self.assertTrue(
            replacement_pickings,
            "Replacement picking not created!",
        )
        self.assertTrue(
            all(move.is_replacement_move for move in replacement_pickings.move_ids),
            "Replacement move missing",
        )

    @users("sale_manager")
    def test_replacement_order_validation_pending_delivery(self):
        """#T-02873: Test replacement is blocked if delivery is not completed."""
        sale_order = self._get_sale_order_with_2_lines()
        first_sol = sale_order.order_line[0]

        self.assertNotEqual(
            sale_order.picking_ids.state,
            "done",
            "Delivery picking should not be in done state",
        )
        wizard = self._create_replacement_wizard(sale_order, first_sol, 1)
        picking_name = sale_order.picking_ids[0].name
        product_name = first_sol.product_id.display_name
        product_qty = first_sol.product_uom_qty
        expected_msg = (
            "You cannot confirm the replacement because the following "
            "delivery is not completed:\n\n"
            f"Product(s): {product_name} "
            f"(Qty: {product_qty}) — Delivery: {picking_name}"
        )
        with self.assertRaises(ValidationError) as err:
            wizard.action_confirm_replacement()
        self.assertEqual(str(err.exception), expected_msg)

    @users("sale_manager")
    def test_replacement_order_validation_on_exceeding_quantity(self):
        """#T-02873: Test replacement fails when requested quantity exceeds allowed."""
        sale_order = self._get_sale_order_with_2_lines()
        first_sol = sale_order.order_line[0]

        allowed_qty = first_sol.product_uom_qty - (first_sol.replaced_qty or 0)
        requested_qty = first_sol.product_uom_qty + 2
        expected_msg = (
            "Following product(s) have exceeded the original quantity:\n\n"
            f"Product '{first_sol.product_id.display_name}': "
            f" Requested {requested_qty}, Allowed {allowed_qty} "
            f"(Original {first_sol.product_uom_qty}, "
            f"Already Replaced {first_sol.replaced_qty or 0})"
        )
        with self.assertRaises(ValidationError) as err:
            self._create_replacement_wizard(
                sale_order,
                first_sol,
                requested_qty,
            )
        self.assertEqual(str(err.exception), expected_msg)

    @users("sale_manager")
    def test_replacement_order_validation_on_zero_quantity(self):
        """#T-02873: Test replacement fails when quantity is zero."""
        sale_order = self._get_sale_order_with_2_lines()
        first_sol = sale_order.order_line[0]
        expected_msg = (
            f"The product(s) {first_sol.product_id.display_name} "
            f"have zero quantity in replacement lines"
        )

        with self.assertRaises(ValidationError) as err:
            self._create_replacement_wizard(sale_order, first_sol, 0)
        self.assertEqual(str(err.exception), expected_msg)

    @users("sale_manager")
    def test_replacement_order_calculate_open_quantities(self):
        """#T-02873: Test validate open quantity calculation for replacement orders."""
        sale_order = self._get_sale_order_with_2_lines()
        pickings = sale_order.picking_ids
        wizard = self.env["replacement.order"].new({"sale_order_id": sale_order.id})

        open_qtys = wizard._calculate_open_quantities(pickings)
        product_qty_to_check = {
            line.product_id.id: line.product_uom_qty for line in sale_order.order_line
        }
        self.assertIsInstance(
            open_qtys,
            dict,
            "Open quantities should be returned as a dictionary",
        )
        for line in sale_order.order_line:
            self.assertIn(line.product_id.id, open_qtys)
            self.assertLessEqual(
                open_qtys[line.product_id.id],
                line.product_uom_qty,
                "Open quantity should not exceed ordered quantity",
            )
        result = wizard._prepare_dict_based_on_picking_code(
            pickings, product_qty_to_check, open_qtys
        )
        self.assertIsInstance(
            result,
            dict,
            "Prepared result should be a dictionary",
        )
        for products in result.values():
            self.assertIsInstance(
                products,
                dict,
                "Each picking entry should be a dictionary of products",
            )
            for pid, (__, qty) in products.items():
                self.assertIn(
                    pid,
                    product_qty_to_check,
                    "Product ID should exist in sale order lines",
                )
                self.assertGreaterEqual(
                    qty,
                    0,
                    "Open quantity should not be negative",
                )

    @users("sale_manager")
    def test_replacement_order_with_cancel_picking(self):
        """#T-02873: Test cancelled replacement pickings do not alter quantities."""
        sale_order = self._get_sale_order_with_2_lines()
        sale_order.picking_ids.button_validate()
        first_sol = sale_order.order_line[0]
        wizard_1 = self._create_replacement_wizard(sale_order, first_sol, 1)
        wizard_1.action_confirm_replacement()

        self.assertEqual(
            first_sol.replaced_qty,
            1,
            "Replaced quantity should be updated after replacement",
        )
        self.assertEqual(
            first_sol.product_uom_qty,
            3,
            "Product UOM quantity should increase after replacement",
        )

        first_replacement_picking = sale_order._get_replacement_pickings()
        first_replacement_picking.action_cancel()

        self.assertEqual(
            first_replacement_picking.state,
            "cancel",
            "Replacement picking should be cancelled",
        )

        self.assertEqual(
            first_sol.replaced_qty,
            0,
            "Replaced quantity should set back after cancellation",
        )
        self.assertEqual(
            first_sol.product_uom_qty,
            2,
            "Product UOM quantity should set back after cancellation",
        )

        wizard_2 = self._create_replacement_wizard(sale_order, first_sol, 1)
        wizard_2.action_confirm_replacement()

        self.assertEqual(
            first_sol.replaced_qty,
            1,
            "Replaced quantity should increase after second replacement",
        )
        self.assertEqual(
            first_sol.product_uom_qty,
            3,
            "Product UOM quantity should increase after second replacement",
        )

    @users("sale_manager")
    def test_multiple_replacement_order(self):
        """#T-02873: Test multiple replacement orders and picking reuse behavior."""
        sale_order = self._get_sale_order_with_2_lines()
        sale_order.picking_ids.button_validate()
        first_sol = sale_order.order_line[0]
        wizard_1 = self._create_replacement_wizard(sale_order, first_sol, 1)
        wizard_1.action_confirm_replacement()
        self.assertEqual(
            first_sol.replaced_qty,
            1,
            "Replaced quantity should be updated after first replacement",
        )
        self.assertEqual(
            first_sol.product_uom_qty,
            3,
            "Product UOM quantity should increase after first replacement",
        )
        first_replacement_picking = sale_order._get_replacement_pickings()
        self.assertTrue(
            first_replacement_picking,
            "Replacement picking not created!",
        )
        self.assertTrue(
            all(
                move.is_replacement_move for move in first_replacement_picking.move_ids
            ),
            "Replacement move missing",
        )
        self.assertNotEqual(
            first_replacement_picking.state,
            "done",
            "Replacement picking should not be in done state",
        )
        self.assertEqual(
            first_replacement_picking.state,
            "assigned",
            "Replacement picking should be in assigned state",
        )
        wizard_2 = self._create_replacement_wizard(sale_order, first_sol, 1)
        wizard_2.action_confirm_replacement()
        self.assertEqual(
            first_sol.replaced_qty,
            2,
            "Replaced quantity should increase after second replacement",
        )
        self.assertEqual(
            first_sol.product_uom_qty,
            4,
            "Product UOM quantity should increase after second replacement",
        )
        self.assertEqual(
            len(sale_order._get_replacement_pickings()),
            1,
            "New replacement picking should not be created",
        )
        self.assertEqual(
            first_replacement_picking.move_ids.product_uom_qty,
            2,
            "Replacement picking move quantity should be updated correctly",
        )
        wizard_3 = self._create_replacement_wizard(sale_order, first_sol, 1)
        with self.assertRaises(ValidationError) as err:
            wizard_3.action_confirm_replacement()
        picking_name = first_replacement_picking.name
        product_name = first_sol.product_id.display_name
        product_qty = first_sol.product_uom_qty - first_sol.replaced_qty
        expected_msg = (
            "You cannot confirm the replacement because the following "
            "delivery is not completed:\n\n"
            f"Product(s): {product_name} "
            f"(Qty: {product_qty}) — Delivery: {picking_name}"
        )
        self.assertEqual(str(err.exception), expected_msg)
        first_replacement_picking.button_validate()
        wizard_3 = self._create_replacement_wizard(sale_order, first_sol, 1)
        with self.assertRaises(ValidationError) as err:
            wizard_3.action_confirm_replacement()
        expected_msg = (
            "You cannot replace more than the original outgoing quantity for "
            "the following sale order lines:\n\nDemoProduct1 - Original Qty : 2.0, "
            "Already Replaced Qty: 2.0, Requested Replacement Qty: 1.0"
        )
        self.assertEqual(str(err.exception), expected_msg)

    @users("sale_manager_and_inventory_manager")
    def test_return_replacement_order(self):
        """# T-02873 Test replacement order flow with return"""
        sale_order = self._get_sale_order_with_2_lines()
        sale_order.picking_ids.button_validate()
        first_sol = sale_order.order_line[0]

        wizard = self._create_replacement_wizard(sale_order, first_sol, 1)
        wizard.action_confirm_replacement()

        self.assertEqual(
            first_sol.replaced_qty,
            1,
            "Replaced quantity should be updated to 1 after confirming replacement",
        )
        self.assertEqual(
            first_sol.product_uom_qty,
            3,
            "Ordered quantity should increase after replacement is created",
        )

        replacement_pickings = sale_order._get_replacement_pickings()
        self.assertTrue(
            replacement_pickings,
            "Replacement picking should be created for the sale order",
        )
        self.assertTrue(
            all(move.is_replacement_move for move in replacement_pickings.move_ids),
            "All moves in replacement picking should be marked as replacement moves",
        )

        self.assertEqual(
            len(sale_order.invoice_ids),
            1,
            "Only one invoice should exist after replacement creation",
        )

        replacement_pickings.button_validate()

        self.assertEqual(
            len(sale_order.invoice_ids),
            1,
            "Validating replacement picking should not create an additional invoice",
        )

        return_wizard = self.env["stock.return.picking"].create(
            {
                "picking_id": replacement_pickings.id,
                "location_id": self.scrap_location.id,
                "product_return_moves": [
                    (
                        0,
                        0,
                        {
                            "product_id": replacement_pickings.move_ids[
                                0
                            ].product_id.id,
                            "quantity": 1,
                            "move_id": replacement_pickings.move_ids[0].id,
                        },
                    ),
                ],
            }
        )
        with self.assertRaises(ValidationError) as err:
            return_wizard.create_returns()
        self.assertEqual(
            str(err.exception), "Return cannot be created for replacement orders."
        )

    @users("sale_manager_and_inventory_manager")
    def test_replaced_qty_to_invoice(self):
        """
        T-02873: Test qty_to_invoice computation when replacement quantities exist.
        """
        sale_order = self._get_sale_order_with_2_lines()
        sale_order.picking_ids.button_validate()

        # --- First sale line: replacement picking DONE ---
        first_line = sale_order.order_line[0]

        wizard = self._create_replacement_wizard(sale_order, first_line, 1)
        wizard.action_confirm_replacement()

        replacement_pickings = sale_order._get_replacement_pickings()
        replacement_pickings.button_validate()

        first_line._compute_qty_to_invoice()
        expected_qty = (
            first_line.qty_delivered - first_line.qty_invoiced - first_line.replaced_qty
        )

        self.assertTrue(
            first_line.replaced_qty,
            "Replaced quantity should be set on the first sale line",
        )
        self.assertEqual(
            first_line.qty_to_invoice,
            expected_qty,
            "qty_to_invoice should exclude replaced quantity once replacement "
            "picking is done",
        )

        # --- Second sale line: replacement picking OPEN ---
        second_line = sale_order.order_line[1]
        wizard = self._create_replacement_wizard(sale_order, second_line, 1)
        wizard.action_confirm_replacement()
        # Do NOT validate replacement picking

        second_line._compute_qty_to_invoice()

        self.assertTrue(
            second_line.replaced_qty,
            "Replaced quantity should be set on the second sale line",
        )
        self.assertEqual(
            second_line.qty_to_invoice,
            second_line.qty_delivered - second_line.qty_invoiced,
            "qty_to_invoice should not exclude replaced quantity while "
            "replacement picking is open",
        )

    @users("sale_manager_and_inventory_manager")
    def test_procurement_qty_with_return_on_original_picking(self):
        """
        T-02873:
        Ensure incoming (return) quantities from the ORIGINAL delivery
        are added back while computing procurement qty for replacement.
        """
        sale_order = self._get_sale_order_with_2_lines()
        original_picking = sale_order.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        original_picking.button_validate()
        self.assertEqual(
            len(sale_order.invoice_ids),
            1,
            "Exactly one invoice should be created after validating original delivery",
        )
        line = sale_order.order_line[0]

        # Create return for ORIGINAL picking
        return_wizard = self.env["stock.return.picking"].create(
            {
                "picking_id": original_picking.id,
                "product_return_moves": [
                    (
                        0,
                        0,
                        {
                            "product_id": original_picking.move_ids[0].product_id.id,
                            "quantity": 1,
                            "move_id": original_picking.move_ids[0].id,
                        },
                    )
                ],
            }
        )
        return_wizard.create_returns()

        incoming_picking = original_picking.return_ids
        self.assertTrue(
            incoming_picking,
            "Incoming picking should be created when the original delivery is returned",
        )
        incoming_picking.button_validate()

        self.assertEqual(
            len(sale_order.invoice_ids),
            2,
            "A refund invoice should be created after validating the return picking",
        )

        # Create replacement for 1 qty AFTER return
        wizard = self._create_replacement_wizard(sale_order, line, 1)
        wizard.action_confirm_replacement()

        replacement_picking = sale_order._get_replacement_pickings().filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        self.assertTrue(
            replacement_picking,
            "Replacement picking should be created after confirming replacement wizard",
        )

        self.assertEqual(
            sum(replacement_picking.move_ids.mapped("product_uom_qty")),
            1,
            "Replacement procurement should consider returned quantity "
            "and create only 1 unit",
        )

        replacement_picking.button_validate()

        self.assertEqual(
            len(sale_order.invoice_ids),
            2,
            "Validating the replacement picking should not create additional invoice",
        )
