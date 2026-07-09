from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_cancel(self):
        """T-02343 export the canceled moves"""
        res = super()._action_cancel()
        # T-02873: Skip processing when the replacement context is present
        # to prevent syncing or updating merged stock moves for replacement orders.
        if self.env.context.get("update_replace_qty", False):
            return res
        canceled_moves = self.filtered(
            lambda m: m.sale_line_id
            and m.state == "cancel"
            and m.picking_type_id.code == "outgoing"
            and not m.is_replacement_move  # T-02873: Do not sync replacement moves.
        )
        if not canceled_moves:
            return res

        scayle_bindings = canceled_moves.mapped("sale_line_id.scayle_bind_ids")
        if not scayle_bindings:
            return res

        cancel_scayle_bindings = scayle_bindings.sudo().filtered(
            lambda b: b.backend_id.auto_export_cancel
        )
        cancel_scayle_bindings.write({"cancel_in_odoo": True})

        for sale_order in cancel_scayle_bindings.mapped("order_id"):
            sale_order.with_context(auto_cancel=True).export_cancel_orders()

        return res

    def _search_picking_for_assignation_domain(self):
        """
        #T-02873 Inherit Method to update domain

        When the context key ``update_replace_qty`` is set:
        - Include pickings that have no backorder.
        - Also include pickings whose backorder is marked as a replacement order
          (``backorder_id.is_replacement_order = True``).

        This ensures that replacement backorders are not excluded while still
        filtering out non-replacement backorders during replacement quantity
        updates.
        """
        domain = super()._search_picking_for_assignation_domain()
        if self.env.context.get("update_replace_qty"):
            domain += [
                "|",
                ("backorder_id.is_replacement_order", "=", True),
                ("backorder_id", "=", False),
            ]
        return domain
