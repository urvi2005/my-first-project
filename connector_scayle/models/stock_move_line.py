from odoo import api, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.depends(
        "quantity",
        "move_id.sale_line_id",
        "move_id.sale_line_id.scayle_bind_ids",
        "move_id.sale_line_id.scayle_bind_ids.eshop_price_with_tax",
    )
    def _compute_eshop_order_price(self):
        """#T-03105: Compute prices from SCAYLE bind ids"""
        res = super()._compute_eshop_order_price()
        for line in self:
            sale_line = line.move_id.sale_line_id
            if not sale_line or not sale_line.product_uom_qty:
                continue
            scayle_lines = sale_line.scayle_bind_ids
            if not scayle_lines:
                continue
            # avg of all scayle lines × quantity
            avg_price = sum(scayle_lines.mapped("eshop_price_with_tax")) / len(
                scayle_lines
            )
            line.eshop_price_with_tax = avg_price * int(line.quantity)

        return res
