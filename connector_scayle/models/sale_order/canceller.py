import logging

from odoo.addons.component.core import Component

_logger = logging.getLogger(__name__)


class SaleOrderCanceller(Component):
    _name = "scayle.sale.order.record.canceller"
    _inherit = "scayle.record.canceller"
    _apply_on = "scayle.sale.order"

    def _after_cancel(self, relation=None):
        """Update the field "cancel_sync_to_scayle" data after cancellation on scayle"""
        if relation:
            for line_binding in relation.mapped("order_line.scayle_bind_ids").filtered(
                lambda b: b.cancel_in_odoo and not b.cancel_sync_to_scayle
            ):
                line_binding.cancel_sync_to_scayle = True
        return super()._after_cancel(relation=relation)
