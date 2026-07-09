# NOTE: Commented Code for future reference as for now we are accepting orders without
# applied fees.
# T-2726: Moved from connector_scayle_cod
# from odoo import _, models

# from odoo.exceptions import ValidationError


# class StockSplitPicking(models.TransientModel):
#     _inherit = "stock.split.picking"

#     def action_apply(self):
#         """
#         Inherit Method: [#T-02492 This method is used for raising
#         validation error if COD as payment method while splitting any picking.]
#         """
#         if any(self.picking_ids.mapped("sale_id.scayle_cod")):
#             raise ValidationError(
#                 _(
#                     "Unfortunately, you cannot split the delivery order as the "
#                     "payment method is COD (Cash on Delivery)!"
#                 )
#             )
#         return super(StockSplitPicking, self).action_apply()
