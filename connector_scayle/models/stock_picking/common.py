import logging

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

from odoo.addons.component.core import Component
from odoo.addons.queue_job.job import identity_exact

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.depends("move_ids", "move_ids.origin_returned_move_id")
    def _compute_return_picking_scayle(self):
        """Compute method to sync return on scayle  based on boolean"""
        for picking in self.filtered(lambda p: p.sale_id and p.sale_id.scayle_bind_ids):
            if any(m.origin_returned_move_id for m in picking.move_ids):
                picking.sync_return_picking_scayle = True
            else:
                picking.sync_return_picking_scayle = False

    @api.depends(
        "move_ids",
        "move_ids.sale_line_id",
        "move_ids.sale_line_id.eshop_shipment_status",
    )
    def _compute_shipment_picking_scayle(self):
        """
        Compute method to make the boolean true when there is full shipment only for
        line having bindings.
        """
        for picking in self.filtered(lambda p: p.sale_id and p.sale_id.scayle_bind_ids):
            if all(
                m.sale_line_id.eshop_shipment_status == "full_shipment"
                for m in picking.move_ids.filtered(
                    lambda move: move.sale_line_id.scayle_bind_ids
                )
            ):
                picking.sync_full_shipment_picking_scayle = True
            else:
                picking.sync_full_shipment_picking_scayle = False

    sync_return_picking_scayle = fields.Boolean(
        compute="_compute_return_picking_scayle", store=True
    )
    sync_full_shipment_picking_scayle = fields.Boolean(
        compute="_compute_shipment_picking_scayle", store=True
    )
    # T-02101 - Fields
    scayle_return_bind_ids = fields.One2many(
        comodel_name="scayle.stock.picking.return",
        inverse_name="odoo_id",
        string="Scayle Bindings",
        copy=False,
    )
    scayle_backend_id = fields.Many2one(
        comodel_name="scayle.backend",
        string="Scayle Picking Backend",
        ondelete="restrict",
    )
    # Moved field from inter_company_so_po_link # T-02556.
    # Field is used to have reference of direct invoice

    def _validate_move_scayle(self):
        """Validate move ids for cancellation and shipment"""
        move_ids = self.move_ids.filtered(
            lambda m: m.sale_line_id
            and not m.origin_returned_move_id
            and m.sale_line_id.eshop_shipment_status
            in ["partial_shipment", "no_shipment"]
            and m.sale_line_id.eshop_cancel_status == "not_cancelled"
            and not m.is_replacement_move  # T-02873: Do not sync replacement moves.
        )
        return move_ids

    def _validate_move_return_scayle(self):
        """Validate move ids for return."""
        move_ids = self.move_ids.filtered(
            lambda m: m.origin_returned_move_id
            and m.sale_line_id
            and m.sale_line_id.scayle_bind_ids.filtered(lambda x: x.shipment_created)
            and m.sale_line_id.eshop_return_status in ["partial_return", "no_return"]
            and not m.is_replacement_move  # T-02873: Do not sync replacement moves.
        )
        return move_ids

    def export_return_items(self, scayle_return_lines=None):
        """#T-02101 Export return order on scayle.

        T-03104 Pass the refunded Scayle lines to the queue job via the
        ``fields`` parameter of ``export_record``. The parameter is only used
        by ``identity_exact`` to differentiate queue jobs for the same picking
        when different lines are refunded in separate operations. It is not
        consumed by the exporter mapper.
        """
        binding = self.env["scayle.stock.picking.return"]
        for pick in self:
            binding.with_company(pick.sudo().scayle_backend_id.company_id).with_delay(
                priority=4,
                identity_key=identity_exact,
                description=binding.scayle_backend_id.get_queue_job_message(
                    model_name=binding._name,
                    is_export=True,
                ),
            ).export_record(pick.scayle_backend_id.sudo(), pick, scayle_return_lines)

    def _validate_export_return_scayle(self):
        """Validate the picking for return export on scayle."""
        self.ensure_one()
        move_ids = self._validate_move_return_scayle()
        # Check if the picking is not drop-shipped then skip for
        # export return item on scayle.
        # T-03090 We also need to skip the sync of picking if it is considered as
        # missing (full order missing or partial qty's BO)
        if not move_ids or (
            self.restrict_return_quick_reimbursement and self.is_missing_product
        ):
            valid_picking = False
        else:
            valid_picking = True
        return valid_picking

    def _export_return_items_on_scayle(self):
        """Method is used to export return items on scayle."""
        valid_picking = self._validate_export_return_scayle()
        if not valid_picking:
            return
        if not self.scayle_backend_id:
            raise ValidationError(
                _("There is no backend set on picking %(picking_name)s.")
                % {"picking_name": self.name}
            )

        if self.sale_id.eshop_return_status == "full_return":
            raise ValidationError(
                _("Return is already sync to scayle for picking %(picking_name)s.")
                % {"picking_name": self.name}
            )

        self.export_return_items()

    def _update_shipment_created_in_order_line(self):
        """
        Method is used to update boolean field shipment created based on
        quantity done in moves in scayle sale line binds when the delivery is done
        in odoo.
        """
        for pick in self.filtered(
            lambda p: p.picking_type_code == "outgoing"
            and p.state == "done"
            and p.sale_id
            and p.sale_id.scayle_bind_ids
            and not p.sync_return_picking_scayle
            and not p.is_replacement_order  # T-02873: Do not sync replacement Order.
        ):
            move_ids = pick._validate_move_scayle()
            for move in move_ids:
                to_deliver_qty = move.quantity
                sale_line_bindings = move.sale_line_id.scayle_bind_ids
                shipped_bindings = sale_line_bindings.filtered(
                    lambda x: x.shipment_created
                )

                remain_shipped_binding = sale_line_bindings - shipped_bindings
                if not remain_shipped_binding:
                    continue
                if to_deliver_qty > len(remain_shipped_binding):
                    raise ValidationError(
                        _(
                            "Shipment has delivered more lines than Scayle items"
                            " available, please check!"
                        )
                    )
                unshipped_bindings = remain_shipped_binding[: int(to_deliver_qty)]
                unshipped_bindings.write(
                    {"shipment_created": True, "stock_shipment_move_id": move.id}
                )
            # Auto shipment export
            if not pick.sync_full_shipment_picking_scayle:
                sale = pick.sale_id
                if not sale.scayle_bind_ids[0].backend_id.auto_export_shipments:
                    continue
                sale.with_context(auto_shipment=True).export_shipment_orders()

    def _get_non_eligible_qty_for_scayle_sync(self, move):
        """#T-03084 New Method: To retrieve the non eligible quantity for scayle return
        sync"""
        self.ensure_one()
        non_eligible_qty = 0
        if not self.restrict_return_quick_reimbursement:
            return non_eligible_qty
        missing_move_lines = move.move_line_ids.filtered(
            lambda ml: ml.location_dest_id in self.picking_type_id.missing_location_ids
            and ml.state == "done"
        )
        # If Move's line have missing location then consider it as non eligible
        if missing_move_lines:
            non_eligible_qty += sum(missing_move_lines.mapped("quantity"))
        # for safety purpose incase no lines with missing still quantity is less then
        # product_uom_qty then remainig should be considered as missing
        else:
            non_eligible_qty += int(move.product_uom_qty) - int(move.quantity)
        return non_eligible_qty

    def update_return_created_in_order_line(self):
        """
        Method is used to update boolean field return created based on
        quantity done in moves in scayle sale line binds when the delivery is returned
        in odoo.
        """
        for pick in self.filtered(
            lambda p: p.picking_type_code == "incoming" and p.sync_return_picking_scayle
        ):
            move_ids = pick._validate_move_return_scayle()
            for move in move_ids:
                to_return_qty = move.quantity
                non_eligible_qty = pick._get_non_eligible_qty_for_scayle_sync(move)
                sale_line_bindings = move.sale_line_id.scayle_bind_ids
                returned_bindings = sale_line_bindings.filtered(
                    lambda x: x.return_created
                )
                remain_return_binding = sale_line_bindings - returned_bindings
                if not remain_return_binding:
                    continue
                allowed_return_lines = remain_return_binding.filtered(
                    lambda x: x.shipment_created
                )
                if to_return_qty > len(allowed_return_lines):
                    raise ValidationError(
                        _(
                            "You cannot validate return because shipment is not yet"
                            " created to scayle for picking %s"
                        )
                        % (pick.return_id.name)
                    )
                # T-03084 Subtract non eligible qty
                to_return_qty = to_return_qty - non_eligible_qty
                unreturned_bindings = allowed_return_lines[: int(to_return_qty)]
                unreturned_bindings.write(
                    {"return_created": True, "stock_return_move_id": move.id}
                )

    def check_partial_quantity_return_and_export_return(
        self, skip_partial_return_check=None
    ):
        """
        New Method: Added method to check for partial quantity for return while
        exporting shipment to scayle. # T-02556
        """
        skip_partial_return_check = skip_partial_return_check or self.browse()
        incoming_pickings = self.filtered(
            lambda pick: all(
                m.origin_returned_move_id for m in pick.move_ids if not m.scrap_id
            )
            and pick.sync_return_picking_scayle
            # T-02873: Do not sync replacement Order.
            and not pick.return_id.is_replacement_order
        ).with_user(SUPERUSER_ID)
        for picking in incoming_pickings:
            prescription_lines = picking.move_ids.filtered(
                lambda m: m.sale_line_id.is_prescription_line
            )
            if picking not in skip_partial_return_check and any(
                float_compare(m.sale_line_id.product_uom_qty, m.product_uom_qty, 2) != 0
                for m in prescription_lines
            ):
                so = picking.sale_id
                message = _(
                    " Automatic returns for multiple frame products are not supported."
                    " Please create a return directly in Scayle and process any"
                    " potential scrap operations in the return"
                    " (Return reference: %s)" % (picking.name)
                )
                activity_user = False
                if hasattr(so, "scayle_bind_ids") and so.scayle_bind_ids:
                    activity_user = so.scayle_bind_ids[0].backend_id.activity_user_id
                activity_user = activity_user or so.user_id
                # Partial returns are not supported due to the inability to accurately
                # identify prices for sub-items, particularly for multiple frame
                # products or prescription lines. Therefore, a mail activity is
                # created as a workaround.
                self.env["connector.base.backend"].create_activity(
                    record=so,
                    message=message,
                    activity_type="connector_settings.mail_activity_data_error",
                    user=activity_user or so.user_id,
                )
                picking.restrict_export_return_to_eshop = True
                continue
            picking._export_return_items_on_scayle()

    def validate_replacement_pickings(self):
        """
        # T-02873 New Method to validate delivered replacement pickings against
        available Scayle items.
        """
        outgoing_pickings = self.filtered(
            lambda picking: (
                picking.picking_type_code == "outgoing"
                and picking.sale_id
                and picking.sale_id.scayle_bind_ids
                and picking.is_replacement_order
            )
        )
        # A replacement order always has a replaced quantity,
        # so it must not deliver more items than the demanded replaced quantity.
        invalid_moves = outgoing_pickings.mapped("move_ids").filtered(
            lambda move: (
                move.sale_line_id
                and not move.origin_returned_move_id
                and move.is_replacement_move
                and move.quantity > move.product_uom_qty
            )
        )
        if invalid_moves:
            raise ValidationError(
                _(
                    "Delivered quantity in the replacement order exceeds the "
                    "requested quantity; please verify."
                )
            )

    def _action_done(self):
        """
        #T-02101 Inherit Method : To validate the picking before exporting
        return on scayle.
        """
        self = self.sudo()
        if not self:
            return super()._action_done()

        for pick in self.filtered(
            lambda x: x.picking_type_code == "incoming" and x.sync_return_picking_scayle
        ):
            # Check the return order quantity should not be greater than
            # ordered quantity - delivered quantity.
            move_ids = pick._validate_move_return_scayle()
            if not move_ids:
                raise ValidationError(
                    _(
                        "You cannot validate return because shipment is "
                        "not yet created to scayle for picking %s" % (pick.name)
                    )
                )
            if any(
                move.quantity > move.sale_line_id.qty_delivered
                for move in move_ids
                if not move.is_sample_move  # Ignore the moves that has sample products
            ):
                raise ValidationError(
                    _("You cannot enter the more quantity than the delivered quantity.")
                )
        res = super()._action_done()
        self._update_shipment_created_in_order_line()
        self.update_return_created_in_order_line()
        self.check_partial_quantity_return_and_export_return()
        self.validate_replacement_pickings()
        return res

    def action_cancel(self):
        """
        Inherit Method : To update the cancellation of delivery in
        odoo in sale line binds.
        """
        result = super().action_cancel()
        for pick in self.filtered(
            lambda p: p.picking_type_code == "outgoing"
            and p.state == "cancel"
            and p.sale_id
            and p.sale_id.scayle_bind_ids
            and not p.sync_return_picking_scayle
            and not p.is_replacement_order  # T-02873: Do not sync replacement Order.
        ):
            move_ids = pick._validate_move_scayle()
            for move in move_ids:
                to_ordered_qty = move.product_uom_qty
                sale_line_bindings = move.sale_line_id.scayle_bind_ids
                canceled_bindings = sale_line_bindings.filtered(
                    lambda x: x.cancel_in_odoo
                )

                remain_canceled_binding = sale_line_bindings - canceled_bindings
                if not remain_canceled_binding:
                    continue
                if to_ordered_qty > len(remain_canceled_binding):
                    raise ValidationError(
                        _(
                            "Shipment has canceled more lines than Scayle items"
                            " available, please check!"
                        )
                    )
                uncancel_bindings = remain_canceled_binding[: int(to_ordered_qty)]
                uncancel_bindings.write({"cancel_in_odoo": True})
        self._adjust_qty_for_cancelled_replacement_pickings()
        return result

    def _adjust_qty_for_cancelled_replacement_pickings(self):
        """
        # T-02873: New Method to adjust sale order line quantities when
        replacement pickings are cancelled to prevent cancelled quantities from
        being considered in `product_uom_qty` during the creation
        of new replacement pickings through procurement.
        """
        canceled_replacement_pickings = self.filtered(
            lambda pick: pick.picking_type_code == "outgoing"
            and pick.state == "cancel"
            and pick.sale_id
            and pick.sale_id.scayle_bind_ids
            and not pick.sync_return_picking_scayle
            and pick.is_replacement_order
        )
        if not canceled_replacement_pickings:
            return
        cancelled_replacement_moves = canceled_replacement_pickings.mapped(
            "move_ids"
        ).filtered(
            lambda move: (
                move.sale_line_id
                and not move.origin_returned_move_id
                and move.is_replacement_move
            )
        )
        for move in cancelled_replacement_moves:
            sale_line = move.sale_line_id
            sale_line.with_context(update_replace_qty=True).write(
                {
                    "product_uom_qty": sale_line.product_uom_qty - move.product_uom_qty,
                    "replaced_qty": sale_line.replaced_qty - move.product_uom_qty,
                }
            )

    def _set_delivery_package_type(self, batch_pack=False):
        """
        #T-02869 Inherit method: Pass context of carrier to
        search appropriate package type
        """
        res = super()._set_delivery_package_type(batch_pack)
        context = res.get("context")
        if self.carrier_id:
            context["current_shipping_carrier"] = self.carrier_id.id
        return res

    def _verify_home_try_on_eligibility(self):
        """
        T-02988 Inherit Method: To check home try-on eligibility with scayle
        binding
        """
        self.ensure_one()
        sale_binding = self.sale_id.scayle_bind_ids
        if not sale_binding:
            return False
        return super()._verify_home_try_on_eligibility()

    @api.depends("sale_id", "sale_id.scayle_bind_ids")
    def _compute_home_try_order(self):
        """
        #T-02988 Inherit Compute Method: To identify picking should be considered as
        Home Try-On or not
        """
        return super()._compute_home_try_order()

    def _create_backorder(self):
        """
        T-02873: Inherit to mark the backorder of a replacement order as a
        replacement order and its moves as replacement moves.
        """
        backorders = super()._create_backorder()
        for backorder in backorders.filtered(
            lambda back: back.backorder_id.is_replacement_order
        ):
            backorder.is_replacement_order = True
            backorder.move_ids.write({"is_replacement_move": True})
        return backorders


class ScayleStockPickingReturn(models.Model):
    _name = "scayle.stock.picking.return"
    _inherit = ["scayle.binding", "api.payload.history"]
    _inherits = {"stock.picking": "odoo_id"}
    _description = "Scayle Stock Picking Return"

    _rec_name = "name"

    # T-02101 - fields
    odoo_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Picking Return",
        required=True,
        ondelete="restrict",
    )


class ScayleStockPickingReturnAdapter(Component):
    _name = "scayle.stock.picking.return.adapter"
    _inherit = "scayle.adapter"
    _apply_on = "scayle.stock.picking.return"

    _eshop_create_model = "item-return"

    def create(self, data):
        """Inherit Method : To add data for return items in array."""
        data = data.get("return_items")
        return super().create(data)
