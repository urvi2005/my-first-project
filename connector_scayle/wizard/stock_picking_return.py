from odoo import models


class ReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    def _create_returns(self):
        """#T-02101 : Validate picking before creating return to export on scayle."""
        if not self.picking_id.sale_id:
            return super()._create_returns()

        new_picking_id, pick_type_id = super()._create_returns()
        new_picking = self.env["stock.picking"].browse(new_picking_id)
        # Add the scayle backend from the sale order.
        if not new_picking.scayle_backend_id and new_picking.sale_id.scayle_bind_ids:
            new_picking.scayle_backend_id = new_picking.sale_id.scayle_bind_ids[
                0
            ].backend_id.id
        return new_picking_id, pick_type_id

    def _get_block_reimbursement_reason(
        self, scayle_shop, total_return_amount, restricted_ecom_category_name
    ):
        """#T-03084 New Method: To prepare the block reimbursement reason"""
        block_reasons = []
        if (
            scayle_shop.threshold_return_amount
            and total_return_amount > scayle_shop.threshold_return_amount
        ):
            block_reasons.append(
                f"Return amount ({total_return_amount}) exceeds threshold "
                f"({scayle_shop.threshold_return_amount})."
            )

        if restricted_ecom_category_name:
            block_reasons.append(
                f"Product category restricted for quick reimbursement: "
                f"{', '.join(restricted_ecom_category_name)}."
            )
        return block_reasons

    def _validate_quick_reimbursement_of_return(self, total_scayle_lines):
        """#T-03084 Inherit Method: To validate the quick reimbursement block and
        reasons by checking the criteria"""
        res, reasons = super()._validate_quick_reimbursement_of_return(
            total_scayle_lines
        )
        sale_order = self.picking_id.sale_id
        scayle_binding = sale_order.scayle_bind_ids and sale_order.scayle_bind_ids[0]
        # Skip if scayle binding not exists
        if not scayle_binding:
            return res, reasons
        # Get the eshop from backend to check the reimbursement configs
        scayle_shop = scayle_binding.backend_id.scayle_shop_id
        is_prevent_quick_reimbursement = scayle_shop.is_prevent_quick_reimbursement
        # Skip if prevent quick reimbursement is false
        if not is_prevent_quick_reimbursement:
            return res, reasons
        # Check all returnable lines > scayle bindings (possible that not in same DO)
        # and gather it's ecom category
        ecommerce_categ_in_return = self.env["ecommerce.category"]
        total_scayle_lines = total_scayle_lines or self.env["scayle.sale.order.line"]
        for line in total_scayle_lines:
            product = line.frame_product_id or line.product_id
            ecommerce_categ_in_return |= product.ecommerce_categ_id

        total_return_amount = 0.0
        # From return wizard we will check each move's selected in it with it's
        # Quantity to calculate the eshop price total(current return which is going
        # to be created)
        for move in self.product_return_moves:
            qty = int(move.quantity)
            bindings = move.move_id.sale_line_id.scayle_bind_ids[:qty]
            # Remove the scayle lines considered in current return
            total_scayle_lines = total_scayle_lines - bindings
            total_return_amount += sum(bindings.mapped("eshop_price_with_tax"))

        # Retrive all the existing return to check combine total of all returns of
        # specific sale order
        existing_returns = sale_order.picking_ids.filtered(
            lambda pick: pick.picking_type_code == "incoming"
            and pick.is_actual_return
            and pick.state != "cancel"
        )
        for move in existing_returns.mapped("move_ids"):
            qty = int(move.product_uom_qty)
            bindings = move.sale_line_id.scayle_bind_ids[:qty]
            # Remove the scayle lines covered in previously created returns
            total_scayle_lines = total_scayle_lines - bindings
            total_return_amount += sum(bindings.mapped("eshop_price_with_tax"))

        # For the remaining lines condsider it's amount
        if total_scayle_lines:
            total_return_amount += sum(
                total_scayle_lines.mapped("eshop_price_with_tax")
            )

        # Get all return move > products > ecommerce categories
        # T-03086: Use frame product category for prescription lines; otherwise
        # fallback to product category
        ecommerce_categ_in_return |= self.product_return_moves.mapped(
            lambda move_line: (
                sale_line.frame_product_id.ecommerce_categ_id
                if (sale_line := move_line.move_id.sale_line_id)
                and sale_line.is_prescription_line
                else move_line.move_id.product_id.ecommerce_categ_id
            )
        )
        # Check restricted ecommerce categories
        restricted_ecom_category_name = ecommerce_categ_in_return.filtered(
            lambda categ: categ in scayle_shop.ecommerce_categ_ids
        ).mapped("name")

        # get the block reasons
        block_reasons = self._get_block_reimbursement_reason(
            scayle_shop, total_return_amount, restricted_ecom_category_name
        )
        if block_reasons:
            return True, block_reasons
        return res, reasons
