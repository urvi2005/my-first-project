from odoo.tests import Form
from odoo.tests.common import users

from .common import recorder
from .test_export_shipment_orders import TestShipmentExport


class TestPickingReturnExport(TestShipmentExport):
    @classmethod
    def setUpClass(cls):
        """#T-02250 Configurations for return of dropship"""
        super().setUpClass()
        cls.pickings = cls.sale_binding.picking_ids
        # The creation of the return was moved from the setup method because
        # generating a return within the setup would affect the parent test case as
        # well. # T-02556

    @users("inventory_manager")
    @recorder.use_cassette("export_picking_return")
    def test_export_return_done_assertions(self):
        """
        # T-02250 We have to export the dropship return explicitly because in
         action-done method of picking, export record uses queue job,
        so it will not do the export.
        """
        # T-02250 Open the wizard for return
        stock_return_picking_form = Form(
            self.env["stock.return.picking"].with_context(
                active_ids=self.pickings.ids,
                active_id=self.pickings.ids[0],
                active_model="stock.picking",
            )
        )
        stock_return_picking = stock_return_picking_form.save()
        self.return_picking_action = stock_return_picking.create_returns()
        self.return_pick = self.env["stock.picking"].browse(
            self.return_picking_action["res_id"]
        )
        for move in self.return_pick.move_ids:
            move.quantity = move.product_uom_qty
        self.return_pick.button_validate()
        binding = self.env["scayle.stock.picking.return"]
        binding.export_record(
            self.return_pick.scayle_backend_id.sudo(), self.return_pick
        )
        picking_return = binding.search(
            [
                ("odoo_id", "=", self.return_pick.id),
            ]
        )
        self.assertEqual(
            picking_return.external_id,
            str(self.return_pick.id),
            "External ID should be matched!",
        )
        self.assertEqual(len(picking_return), 1, "Return Binding should be exist")
        self.assertEqual(
            picking_return.state, "done", "Return Binding State must be done"
        )
        self.assertEqual(
            len(picking_return.move_ids), 2, "Unexpected no. of moves encountered!"
        )
        move0 = picking_return.move_ids[0]
        move1 = picking_return.move_ids[1]
        self.assertEqual(move0.quantity, 2, "Quantity should be matched!")
        self.assertEqual(move1.quantity, 1, "Quantity should be matched!")
