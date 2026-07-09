# from odoo.exceptions import ValidationError
from odoo.exceptions import UserError
from odoo.tests.common import users

from .common import ScayleTestCases


class ScayleCODPaymentMethod(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Configurations for Sale Order #T-02492"""
        super().setUpClass()

    @users("sale_manager")
    def test_01_sale_order_line_unlink_for_cod(self):
        """
        Added Test cases to check whether order line is being deleted or not for cod
        payment method #T-02512.
        """
        self.binding_model.import_record(
            backend=self.cz_scayle_backend,
            external_id=self.external_id,
            data=self.scayle_cz_order_payload,
        )
        self.sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id)]
        )
        # If COD then could not delete order line. # T-02512
        with self.assertRaises(UserError):
            self.sale_binding.odoo_id.order_line[0].unlink()

    @users("sale_manager")
    def test_02_cod_payment_method(self):
        """Added test cases for checking COD payment method. #T-02492"""
        self.binding_model.import_record(
            backend=self.cz_scayle_backend,
            external_id=self.external_id,
            data=self.scayle_cz_order_payload,
        )
        self.sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id)]
        )
        self.sale_binding.odoo_id.action_confirm()
        self.assertTrue(
            self.sale_binding.odoo_id.eshop_cod, "Scayle COD should be True!"
        )
        self.assertEqual(
            self.sale_binding.odoo_id.eshop_payment_method,
            self.cz_scayle_backend.cod_payment_method,
            "Payment Method should be COD!",
        )
        # Check value of eshop_cod at picking level. # T-02492
        self.assertTrue(
            self.sale_binding.odoo_id.picking_ids[0].eshop_cod,
            "Scayle COD should be True!",
        )

    @users("inventory_manager")
    def test_03_non_cod_payment_method(self):
        """Added test cases for checking COD payment method. #T-02492"""
        self.scayle_cz_order_payload.update({"paymentMethod": "accounting"})
        self.binding_model.import_record(
            backend=self.cz_scayle_backend,
            external_id=self.external_id,
            data=self.scayle_cz_order_payload,
        )
        self.sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id)]
        )
        self.sale_binding.odoo_id.action_confirm()
        moves = self.env["stock.move"].search(
            [
                (
                    "id",
                    "=",
                    self.sale_binding.odoo_id.picking_ids.move_ids[0].id,
                )
            ]
        )
        self.assertEqual(
            len(self.sale_binding.odoo_id.picking_ids.ids),
            1,
            "There should be only one picking before split.",
        )
        wizard = (
            self.env["stock.split.picking"]
            .with_context(active_ids=self.sale_binding.odoo_id.picking_ids.ids)
            .create(
                {
                    "mode": "selection",
                    "move_ids": [
                        (
                            6,
                            False,
                            moves.ids,
                        )
                    ],
                }
            )
        )
        # If not COD then split functionality should work. # T-02492
        wizard.action_apply()
        # Check COD should be true as COD is being passed from scayle as payment method.
        # T-02492
        self.assertEqual(
            len(self.sale_binding.odoo_id.picking_ids.ids),
            2,
            "There should be 2 picking after split.",
        )
        self.assertFalse(
            self.sale_binding.odoo_id.eshop_cod, "Scayle COD should be False."
        )
        self.assertEqual(
            self.sale_binding.odoo_id.eshop_payment_method,
            "accounting",
            "Payment Method should be accounting.",
        )
        # Check value of eshop_cod at picking level. # T-02492
        self.assertFalse(
            self.sale_binding.odoo_id.picking_ids[0].eshop_cod,
            "Scayle COD should be False!",
        )
