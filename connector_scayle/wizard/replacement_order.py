from collections import defaultdict

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class ReplacementOrder(models.TransientModel):
    _name = "replacement.order"
    _description = "Replacement Order"

    sale_order_id = fields.Many2one(
        comodel_name="sale.order", string="Original Sale Order", required=True
    )
    replacement_reason = fields.Char(required=True)
    replacement_order_line_ids = fields.One2many(
        comodel_name="replacement.order.line",
        inverse_name="replacement_order_id",
        string="Replacement Lines",
        compute="_compute_replacement_order_lines",
        readonly=False,
        store=True,
    )

    @api.depends("sale_order_id")
    def _compute_replacement_order_lines(self):
        """
        T-02873 Automatically populate the replacement_order_line_ids field
        with all non-prescription lines from the selected sale order.
        """
        for wizard in self:
            wizard.replacement_order_line_ids = [(5, 0, 0)]
            if not wizard.sale_order_id:
                continue

            replacement_lines = []
            for line in wizard.sale_order_id.order_line:
                if line.is_prescription_line:
                    continue
                replacement_lines.append(
                    (
                        0,
                        0,
                        {
                            "sale_order_line_id": line.id,
                            "product_id": line.product_id.id,
                            "quantity": line.product_uom_qty - line.replaced_qty,
                        },
                    )
                )
            # Set the filtered non-prescription lines on the wizard
            wizard.replacement_order_line_ids = replacement_lines

    @api.constrains("replacement_order_line_ids")
    def _check_replacement_line_quantities(self):
        """
        #T-02873 Validate the replacement lines.
        """
        for record in self:
            replacement_lines = record.replacement_order_line_ids
            # Validate that replacement lines exist
            if not replacement_lines:
                raise ValidationError(_("Please add at least one replacement line."))
            lines_with_zero_qty = replacement_lines.filtered(
                lambda line: line.quantity <= 0
            )
            # Validate lines with zero quantity
            if lines_with_zero_qty:
                raise ValidationError(
                    _("The product(s) %s have zero quantity in replacement lines")
                    % ", ".join(lines_with_zero_qty.mapped("product_id.display_name"))
                )
            # ❌ Validate decimal quantities (e.g. 1.7, 0.5)
            decimal_qty_lines = replacement_lines.filtered(
                lambda line: float_compare(
                    line.quantity, int(line.quantity), precision_digits=2
                )
                != 0
            )
            if decimal_qty_lines:
                raise ValidationError(
                    _(
                        "Decimal quantities are not allowed for replacement lines. "
                        "Please use whole numbers only for: %s"
                    )
                    % ", ".join(decimal_qty_lines.mapped("product_id.display_name"))
                )

            exceeding_quantity_lines = replacement_lines.filtered(
                lambda line: line.sale_order_line_id
                and line.quantity
                > (
                    line.sale_order_line_id.product_uom_qty
                    - line.sale_order_line_id.replaced_qty
                )
            )
            if not exceeding_quantity_lines:
                continue
            error_messages = "\n".join(
                _(
                    "Product '%(product)s': "
                    " Requested %(requested)s, Allowed %(allowed)s "
                    "(Original %(ordered)s, Already Replaced %(replaced)s)"
                )
                % {
                    "product": line.product_id.display_name,
                    "ordered": line.sale_order_line_id.product_uom_qty,
                    "replaced": line.sale_order_line_id.replaced_qty or 0,
                    "allowed": (
                        line.sale_order_line_id.product_uom_qty
                        - (line.sale_order_line_id.replaced_qty or 0)
                    ),
                    "requested": line.quantity,
                }
                for line in exceeding_quantity_lines
            )
            raise ValidationError(
                _("Following product(s) have exceeded the original quantity:\n\n%s")
                % error_messages
            )

    def _update_sale_line_for_replacement(self):
        """#T-02873 New Method: To update sale lines based on replacement information"""
        for line in self.replacement_order_line_ids:
            sale_line = line.sale_order_line_id.with_context(update_replace_qty=True)
            # Add replacement qty to original SOL
            sale_line.write(
                {
                    "product_uom_qty": sale_line.product_uom_qty + line.quantity,
                    "replaced_qty": sale_line.replaced_qty + line.quantity,
                }
            )

    def action_confirm_replacement(self):
        """T-02873 Update original sale order lines with replacement qty."""
        self.ensure_one()

        # Ensure old pickings done
        self._check_existing_pickings_done()
        sale_order = self.sale_order_id
        # Store existing pickings so we can detect new ones
        existing_move_ids = sale_order.picking_ids.move_ids.ids
        self._update_sale_line_for_replacement()
        # Identify newly created moves
        all_moves = sale_order.picking_ids.move_ids
        new_moves = all_moves.filtered(lambda m: m.id not in existing_move_ids)
        # Mark picking(s) containing replacement moves
        replacement_pickings = new_moves.mapped("picking_id")
        replacement_pickings.write({"is_replacement_order": True})
        # Always mark replacement moves
        new_moves.write({"is_replacement_move": True})
        # Optionally, post message
        # Generate chatter message for the sale order
        msg_lines = self._generate_order_messages(replacement_pickings)
        # Post the message if there are any lines to show
        if msg_lines:
            self._post_message(msg_lines)
        return True

    def _generate_order_messages(self, replacement_pickings):
        """#T-02873 Generate replacement messages for outgoing pickings."""
        replacement_out_pickings = replacement_pickings.filtered(
            lambda pick: pick.picking_type_id.code == "outgoing"
        )
        grouped_moves = defaultdict(list)
        # Group moves by picking
        for move in replacement_out_pickings.mapped("move_ids"):
            grouped_moves[move.picking_id.name].append(move)

        messages = []
        for picking_name, moves in grouped_moves.items():
            product_details = "".join(
                f"<li class='mb-0'>{move.product_id.display_name} "
                f"(Qty: {move.product_uom_qty})</li>"
                for move in moves
            )
            messages.append(
                Markup(
                    f"<b class='mb-0'>Picking:</b> {picking_name}<br/>"
                    f"<b class='mb-0'>Products:</b>"
                    f"<ul class='mb-0'>{product_details}</ul>"
                )
            )
        return messages

    def _check_existing_pickings_done(self):
        """
        #T-02873 Ensure all previous pickings are completed before replacement,
        handling multiple returns efficiently.
        """
        product_qty_to_check = {
            line.product_id.id: line.quantity
            for line in self.replacement_order_line_ids
        }
        sale_order = self.sale_order_id
        replacement_orders = sale_order._get_replacement_pickings()
        pickings = sale_order.picking_ids
        self._check_cancelled_pickings_for_products(
            product_ids=set(product_qty_to_check.keys()),
            pickings=pickings - replacement_orders,  # Only check for original pickings
        )
        all_pickings = (pickings | replacement_orders).filtered(
            lambda p: (
                p.state not in ("cancel", "done") and p.picking_type_code == "outgoing"
            )
        )
        open_qtys = self._calculate_open_quantities(all_pickings)
        pending_delivery = self._prepare_dict_based_on_picking_code(
            all_pickings, product_qty_to_check, open_qtys
        )
        message_list = []

        def format_products(products_dict):
            return ", ".join(
                f"{name} (Qty: {qty})" for name, qty in sorted(products_dict.values())
            )

        if pending_delivery:
            for pick_name, products_dict in pending_delivery.items():
                message_list.append(
                    _("Product(s): %(products)s — Delivery: %(returns)s")
                    % {
                        "products": format_products(products_dict),
                        "returns": pick_name,
                    }
                )
        if message_list:
            delivery_place_holder = (
                "delivery is" if len(message_list) == 1 else "deliveries are"
            )
            raise ValidationError(
                _(
                    "You cannot confirm the replacement because the following"
                    " %(delivery_place_holder)s not completed:\n\n%(details)s"
                )
                % {
                    "delivery_place_holder": delivery_place_holder,
                    "details": "\n".join(message_list),
                }
            )
        # T-03029: Validate replacement quantity.
        self._check_replacement_qty_not_exceed_original()

    def _get_original_outgoing_qty(self, sale_line):
        """
        #T-03029 New method to return total quantity delivered for a sale order line,
        ignoring replacement moves and considering only done outgoing pickings.
        """
        return sum(
            move.quantity
            for move in sale_line.move_ids
            if (
                move.state == "done"
                and not move.is_replacement_move
                and move.picking_id
                and move.picking_id.picking_type_code == "outgoing"
            )
        )

    def _check_replacement_qty_not_exceed_original(self):
        """
        #T-03029 Ensure total replacement quantity per sale order line does not exceed
        original outgoing quantity from the given pickings.
        """
        # Single dict to track original delivered qty already computed per sale line
        original_by_line = {}
        errors = []
        for repl_line in self.replacement_order_line_ids:
            sale_line = repl_line.sale_order_line_id
            # Compute original delivered qty only once per sale line
            if sale_line not in original_by_line:
                original_by_line[sale_line] = self._get_original_outgoing_qty(sale_line)

            original_qty = original_by_line[sale_line] or 0.0
            # Requested replacement qty
            requested_qty = repl_line.quantity
            already_replaced = sale_line.replaced_qty
            # Skip if the replacement qty is within limits
            if already_replaced + requested_qty <= original_qty:
                continue
            # Validate requested + already replaced qty
            errors.append(
                _(
                    "%(product)s - "
                    "Original Qty : %(original)s, "
                    "Already Replaced Qty: %(already)s, "
                    "Requested Replacement Qty: %(current)s"
                )
                % {
                    "product": sale_line.product_id.name,
                    "original": original_qty,
                    "already": already_replaced,
                    "current": requested_qty,
                }
            )

        # Collect all errors and raise once.
        if errors:
            raise ValidationError(
                _(
                    "You cannot replace more than the original outgoing quantity "
                    "for the following sale order lines:\n\n%(errors)s"
                )
                % {"errors": "\n".join(errors)}
            )

    def _calculate_open_quantities(self, pickings):
        """#T-02873 Calculate open quantities for all products in pending moves."""
        open_qtys = {}
        for move in pickings.mapped("move_ids"):
            move_product_id = move.product_id.id
            if move_product_id not in open_qtys:
                order_line = self.sale_order_id.order_line.filtered(
                    lambda line, pid=move_product_id: line.product_id.id == pid
                )
                # Start with ordered quantity from order_line
                open_qtys[move_product_id] = (
                    order_line.product_uom_qty - order_line.replaced_qty
                )
            # Deduct move quantity from open_qty
            open_qtys[move_product_id] -= move.product_uom_qty
        return open_qtys

    def _prepare_dict_based_on_picking_code(
        self, pickings, product_qty_to_check, open_qtys
    ):
        """
        #T-02873 New method to prepare dict for based on picking type code
        grouped by picking type (delivery/return) and picking name.

        Args:
            pickings: Recordset of all pending stock pickings
            product_qty_to_check: Dict of {product_id: replacement_qty}
            open_qtys: Dict of {product_id: available_qty}

        Returns:
            Tuple of (delivery_issues, return_issues) where each is a dict of:
            {picking_name: {product_id: (product_name, quantity)}}
            e.g : {'WH/OUT/01011': {85: ('[24434] 24434', 1.0)}}
        """
        pending_delivery = {}
        for move in pickings.mapped("move_ids"):
            product_id = move.product_id.id

            if product_id not in product_qty_to_check:
                continue

            # Skip if available quantity can cover replacement
            if open_qtys[product_id] >= product_qty_to_check[product_id]:
                continue

            # Get picking and product info
            picking = move.picking_id
            product_info = (move.product_id.display_name, move.product_uom_qty)

            # Initialize picking entry if not exists
            if picking.name not in pending_delivery:
                pending_delivery[picking.name] = {}

            # Add or update product quantity in the picking
            if product_id not in pending_delivery[picking.name]:
                # First occurrence of this product in this picking
                pending_delivery[picking.name][product_id] = product_info
            else:
                # Product already exists in this picking - sum quantities
                existing_qty = pending_delivery[picking.name][product_id][1]
                pending_delivery[picking.name][product_id] = (
                    product_info[0],  # Keep same product name
                    existing_qty + product_info[1],  # Sum quantities
                )

        return pending_delivery

    def _check_cancelled_pickings_for_products(self, product_ids, pickings):
        """
        #T-02873 Raise an error if any outgoing picking for the given products
        was cancelled.
        """
        cancelled_pickings = pickings.filtered(
            lambda picking: picking.state == "cancel"
            and picking.picking_type_code == "outgoing"
        )
        cancelled_moves = cancelled_pickings.mapped("move_ids").filtered(
            lambda move: move.product_id.id in product_ids
        )
        if cancelled_moves:
            product_names = ", ".join(cancelled_moves.mapped("product_id.display_name"))
            raise ValidationError(
                _(
                    "You cannot create a replacement order for the following "
                    "product(s) because their delivery was cancelled:\n%s"
                )
                % product_names
            )

    def _post_message(self, msg_lines):
        """#T-02873 Post replacement delivery message."""
        reason = self.replacement_reason
        header = f"<b>Replacement Order(s) Created</b><br/><b>Reason:</b> {reason}<br/>"
        body = header + "<br/>".join(msg_lines)
        self.sale_order_id.message_post(body=Markup(body))


class ReplacementOrderLine(models.TransientModel):
    _name = "replacement.order.line"
    _description = "Replacement Order Line"

    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        required=True,
        domain="[('id', '=', product_id)]",
    )
    quantity = fields.Float(digits="Product Unit of Measure", required=True)
    replacement_order_id = fields.Many2one(
        comodel_name="replacement.order", string="Replacement Order", required=True
    )
    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line", string="Original Sale Order Line", required=True
    )
