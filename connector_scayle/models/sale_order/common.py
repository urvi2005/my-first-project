import ast
import json
import logging
from collections import defaultdict

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import html_escape
from odoo.tools.misc import ustr

from odoo.addons.component.core import Component
from odoo.addons.connector.exception import MappingError
from odoo.addons.queue_job.job import identity_exact

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # T-02935 Added new fields
    blacklist_ids = fields.Many2many(
        "blacklist.customer.filter",
        string="Matching Blacklist Records",
    )
    is_blacklisted = fields.Boolean(
        compute="_compute_is_blacklisted",
        store=True,
    )

    @api.depends("blacklist_ids")
    def _compute_is_blacklisted(self):
        """
        #T-02935 Compute method to set the boolean field if order
        # have blacklist_ids
        """
        for order in self:
            order.is_blacklisted = bool(order.blacklist_ids)

    @api.depends("order_line", "order_line.eshop_shipment_status", "scayle_bind_ids")
    def _compute_shipment_status(self):
        """
        #T-02155 Add compute method to add shipment status per order level.
        #T-02726: Inherit method from connector base ecommerce
        """
        res = super()._compute_shipment_status()
        for order in self.filtered(lambda sale: sale.scayle_bind_ids):
            order_line = order.order_line.filtered(
                lambda line: line.eshop_cancel_status == "not_cancelled"
            )
            if all(
                line.eshop_shipment_status == "full_shipment" for line in order_line
            ):
                order.eshop_shipment_status = "full_shipment"
            elif all(
                line.eshop_shipment_status == "no_shipment" for line in order_line
            ):
                order.eshop_shipment_status = "no_shipment"
            elif any(
                line.eshop_shipment_status in ["partial_shipment", "full_shipment"]
                for line in order_line
            ):
                order.eshop_shipment_status = "partial_shipment"
        return res

    @api.depends("order_line", "order_line.eshop_return_status", "scayle_bind_ids")
    def _compute_return_status(self):
        """#T-02155 Add compute method to add the return status per order level."""
        res = super()._compute_return_status()
        for order in self.filtered(lambda sale: sale.scayle_bind_ids):
            order_line = order.order_line.filtered(
                lambda line: line.eshop_cancel_status == "not_cancelled"
            )
            if all(line.eshop_return_status == "full_return" for line in order_line):
                order.eshop_return_status = "full_return"
            elif all(line.eshop_return_status == "no_return" for line in order_line):
                order.eshop_return_status = "no_return"
            elif any(
                line.eshop_return_status in ["partial_return", "full_return"]
                for line in order_line
            ):
                order.eshop_return_status = "partial_return"
        return res

    @api.depends("order_line", "order_line.eshop_cancel_status", "scayle_bind_ids")
    def _compute_cancel_status(self):
        """Add compute method to add cancel status per order level."""
        res = super()._compute_cancel_status()
        for order in self.filtered(lambda sale: sale.scayle_bind_ids):
            if all(
                line.eshop_cancel_status == "cancelled" for line in order.order_line
            ):
                order.eshop_cancel_status = "cancelled"
            elif all(
                line.eshop_cancel_status == "not_cancelled" for line in order.order_line
            ):
                order.eshop_cancel_status = "not_cancelled"
            elif any(
                line.eshop_cancel_status in ["partial_cancelled", "cancelled"]
                for line in order.order_line
            ):
                order.eshop_cancel_status = "partial_cancelled"
        return res

    # Added compute field to get prices from binding level. # T-02556
    @api.depends(
        "scayle_bind_ids",
        "scayle_bind_ids.eshop_price_with_tax",
        "scayle_bind_ids.eshop_price_without_tax",
        "scayle_bind_ids.eshop_tax_amount",
        "scayle_bind_ids.eshop_shipping_tax_amount",
        "scayle_bind_ids.eshop_shipping_without_tax_price",
        "scayle_bind_ids.eshop_shipping_with_tax_price",
        "scayle_bind_ids.eshop_shipping_tax_rate",
    )
    def _compute_eshop_order_price(self):
        """#T-02556 Compute the prices from scayle order bind ids"""
        res = super()._compute_eshop_order_price()
        for order in self:
            bind_id = order.scayle_bind_ids[:1]
            order.eshop_price_with_tax = bind_id.eshop_price_with_tax
            order.eshop_price_without_tax = bind_id.eshop_price_without_tax
            order.eshop_tax_amount = bind_id.eshop_tax_amount
            order.eshop_shipping_tax_amount = bind_id.eshop_shipping_tax_amount
            order.eshop_shipping_without_tax_price = (
                bind_id.eshop_shipping_without_tax_price
            )
            order.eshop_shipping_with_tax_price = bind_id.eshop_shipping_with_tax_price
            order.eshop_shipping_tax_rate = bind_id.eshop_shipping_tax_rate
        return res

    scayle_bind_ids = fields.One2many(
        comodel_name="scayle.sale.order",
        inverse_name="odoo_id",
        string="eShop Bindings",
        copy=False,
    )
    scayle_order_id = fields.Char(
        string="eShop Order ID", compute="_compute_scayle_order_id", store=True
    )

    # Added new field # T-02556.
    scayle_shop_id = fields.Many2one(
        string="eShop",
        comodel_name="scayle.shop",
        readonly=True,
    )

    scayle_line_ids = fields.Many2many(
        comodel_name="scayle.sale.order.line",
        relation="scayle_sale_order_line_rel",
        string="eShop Sale Order Line",
        copy=False,
        readonly=True,
        compute="_compute_scayle_sale_order_line",
    )

    @api.depends("order_line", "order_line.scayle_bind_ids")
    def _compute_scayle_sale_order_line(self):
        """
        #T-02556 Compute the sale order line for prices from scayle sale line binding.
        """
        for order in self:
            if not order.scayle_bind_ids:
                order.scayle_line_ids = False
                continue
            order.scayle_line_ids = order.order_line.scayle_bind_ids

    @api.depends("scayle_bind_ids", "scayle_bind_ids.external_id")
    def _compute_scayle_order_id(self):
        """
        Assign value of external id of first
        binding record to scayle order id  # T-02076
        """
        for order in self:
            order.scayle_order_id = order.scayle_bind_ids[:1].external_id

    def get_canceled_so(self):
        """#T-02343 Return the imported and canceled SOs"""
        return self.filtered(lambda so: so.scayle_bind_ids and so.state == "cancel")

    def action_cancel(self):
        """
        Inherit method to auto export the cancel on scayle when main
        company so cancel based on boolean field auto_export_cancel
        by default it's true.
        """
        result = super().action_cancel()
        if isinstance(result, dict):
            return result
        cancel_orders = self.get_canceled_so()
        if not cancel_orders:
            return result
        order_line_bind_ids = self.env["scayle.sale.order.line"]
        for order in cancel_orders:
            sol_scayle_bind_ids = order.order_line.scayle_bind_ids
            if not order.picking_ids:
                order_line_bind_ids = sol_scayle_bind_ids.filtered(
                    lambda line: not line.cancel_in_odoo
                )
                order_line_bind_ids.sudo().write({"cancel_in_odoo": True})
            else:
                order.validate_cancel_picking()
            if not order.scayle_bind_ids[0].sudo().backend_id.auto_export_cancel:
                continue
            if not sol_scayle_bind_ids.filtered(
                lambda line: line.cancel_in_odoo and not line.cancel_sync_to_scayle
            ):
                continue
            # change from MR !1298
            if not order.picking_ids:
                order.with_context(auto_cancel=True).export_cancel_orders()
        return result

    def export_cancel_orders(self):
        for binding in self.scayle_bind_ids:
            if self._context.get("auto_cancel"):
                self.env["scayle.sale.order"].with_delay(
                    priority=5,
                    identity_key=identity_exact,
                    description=binding.backend_id.get_queue_job_message(
                        model_name="scayle.sale.order", message="Export Cancel Record"
                    ),
                ).export_cancel_record(
                    binding.backend_id.sudo(),
                    binding.external_id,
                    relation=binding.odoo_id,
                )
            else:
                self.validate_cancel_picking()
                try:
                    self.env["scayle.sale.order"].export_cancel_record(
                        binding.backend_id.sudo(),
                        binding.external_id,
                        relation=binding.odoo_id,
                    )
                except Exception as ex:
                    raise ValidationError(_("%s") % (ustr(ex))) from ex

    def validate_create_shipment_picking(self):
        """Validate picking to create shipment on scayle."""
        self.ensure_one()
        if self.eshop_shipment_status == "full_shipment":
            raise ValidationError(
                _(
                    "The shipment is already sync to scayle for "
                    "sale order %(sale_order)s."
                )
                % {"sale_order": self.name}
            )

        picking_ids = self.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing"
            and p.state == "done"
            and not p.sync_return_picking_scayle
            and not p.sync_full_shipment_picking_scayle
        )
        if not picking_ids:
            raise ValidationError(_("There is no picking to create shipment on scayle"))

        if any(not pick._validate_move_scayle() for pick in picking_ids):
            raise ValidationError(
                _("The picking moves are not valid to create shipment on scayle.")
            )

    def export_shipment_orders(self):
        """Export Shipment order on scayle"""
        try:
            for binding in self.scayle_bind_ids:
                if self._context.get("auto_shipment"):
                    binding.with_company(
                        binding.sudo().backend_id.company_id
                    ).with_delay(
                        priority=5,
                        identity_key=identity_exact,
                        description=binding.backend_id.get_queue_job_message(
                            model_name=binding._name,
                            is_export=True,
                        ),
                    ).export_record(binding.backend_id.sudo(), self)
                else:
                    self.validate_create_shipment_picking()
                    binding.export_record(binding.backend_id.sudo(), self)
        except Exception as ex:
            raise ValidationError(_("%s") % (ustr(ex))) from ex

    def _cron_export_shipment_orders(self):
        """Add schedule action to export the return order on scayle."""
        orders = self.env["sale.order"].search(
            [
                ("scayle_bind_ids", "!=", False),
                ("eshop_shipment_status", "in", ["partial_shipment", "no_shipment"]),
            ]
        )
        for order in orders:
            picking_ids = order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == "outgoing"
                and p.state == "done"
                and not p.sync_return_picking_scayle
                and not p.sync_full_shipment_picking_scayle
            )
            if not picking_ids:
                continue
            if any(not pick._validate_move_scayle() for pick in picking_ids):
                continue
            order.with_context(auto_shipment=True).export_shipment_orders()
        return True

    def action_open_in_eshop_panel(self):
        """T-02471 Action for Open in scayle button on form view header"""
        super().action_open_in_eshop_panel()
        self.ensure_one()
        if not self.scayle_bind_ids:
            raise ValidationError(_("Not Enough data to open record on scayle!!!"))
        return self.sudo().scayle_bind_ids[:1].action_open_in_scayle_panel()

    @api.model
    def _get_order_tags(self, eshop_collection_point, products, **kwargs):
        """#T-02779 Method Inherit: Append designer tag in tags to add in Sales Order"""
        tags = []
        order_type = kwargs.get("order_type")
        if products and any(prod.get("is_designer_line") for prod in products.values()):
            tags.append("DesignerOrder")
        if products and any(
            prod.get("is_subscription_line") for prod in products.values()
        ):
            tags.append("SUB")
        # T-02946 : Set tags based on order_type value
        if order_type and order_type.lower() == "za":
            tags.append("ZA")
        if order_type and order_type.lower() == "oa":
            tags.append("OA")
        # T-03043 : Set tags for MIX order.
        if kwargs.get("is_mltp_order"):
            tags.append("MLTP")
        kwargs["tags"] = tags
        return super()._get_order_tags(eshop_collection_point, products, **kwargs)

    def check_blacklist_values(self):
        """T-02935 New method : for checking blacklisted partner"""
        self.ensure_one()
        reasons = {
            "customer": False,
            "products": [],
        }
        matched_blacklists = self.env["blacklist.customer.filter"]
        if not self.scayle_bind_ids:
            return {
                "blacklists": matched_blacklists,
                "reasons": reasons,
            }
        blacklisted_products = self.env["product.product"]
        # T-02935 Loop over blacklist filters
        for bl in self.env["blacklist.customer.filter"].search([]):
            if not bl.domain:
                continue
            # T-2935 Safely converts a domain string into a
            # Python list for Odoo searches.
            domain = ast.literal_eval(bl.domain)
            # T-03107 if partner filter partner
            if bl.domain_type == "partner":
                bl_partner = self.partner_shipping_id.filtered_domain(domain)
                if bl_partner:
                    matched_blacklists |= bl
                    reasons["customer"] = True
            # T-03107 if product filter on product
            elif bl.domain_type == "product":
                products = self.order_line.mapped("frame_product_id")
                bl_products = products.filtered_domain(domain)
                if bl_products:
                    matched_blacklists |= bl
                    blacklisted_products |= bl_products
        if blacklisted_products:
            # dict to mapped proper KB lines with frame product
            line_by_frame = {}

            for line in self.order_line.filtered(
                lambda line,
                blacklisted_products=blacklisted_products: line.frame_product_id
                in blacklisted_products
            ):
                line_by_frame.setdefault(
                    line.frame_product_id,
                    self.env["sale.order.line"],
                )
                line_by_frame[line.frame_product_id] |= line
            # Loop through to get product values
            product_info = [
                {
                    "frame_product": fp.display_name,
                    "finished_products": line_by_frame[fp].mapped(
                        "product_id.display_name"
                    ),
                }
                for fp in blacklisted_products
            ]
            reasons["products"] = product_info
        self.blacklist_ids = matched_blacklists
        return {
            "blacklists": matched_blacklists,
            "reasons": reasons,
        }

    def create_reservation(self):
        """T-02935 Inherit Method: To Create Reservation in FL"""
        blacklisted_so = self.filtered(lambda o: o.is_blacklisted)
        return super(SaleOrder, blacklisted_so).create_reservation()

    def _should_apply_mltp_consolidation(self):
        """
        # T-03108:Inherit Method: Check if MLTP consolidation should be applied.

        Check backend setting to determine if MLTP consolidation
        should be applied to non-NDL orders.

        Returns:
            bool: True if MLTP consolidation is enabled in backend
        """
        if self.scayle_bind_ids and not self.is_ndl_order:
            return self.scayle_bind_ids[:1].backend_id.apply_mltp_consolidation
        return super()._should_apply_mltp_consolidation()

    def action_confirm(self):
        """
        Inherit Method : To add sample product moves in picking #T-02772
        """
        res = super().action_confirm()
        for order in self:
            if not order.scayle_bind_ids:
                continue
            allow_sample_products = order.scayle_bind_ids[
                :1
            ].backend_id.allow_sample_products
            if not allow_sample_products:
                continue
            picking_ids = order.picking_ids.filtered(
                lambda pick: pick.picking_type_code == "outgoing"
                and pick.state not in ["draft", "done", "cancel"]
                and not any(move.is_sample_move for move in pick.move_ids)
            )
            if not picking_ids:
                continue
            # Add sample product moves in DO
            moves = picking_ids.mapped("move_ids")
            sample_move_data_list = self.create_sample_product_move(moves)
            if sample_move_data_list:
                new_sample_moves = self.env["stock.move"].create(sample_move_data_list)
                # `_action_confirm` on all newly created moves
                new_sample_moves._action_confirm()
        return res

    def process_order(self):
        """T-02935 New Method : To process the order if partner is blacklisted"""
        # T-03091: Upated to is_blacklisted to support archived blacklist records
        for order in self.filtered(lambda o: o.is_blacklisted and o.scayle_bind_ids):
            order.is_blacklisted = False
            order.action_unlock()
            order.action_confirm()
        return True

    def process_action_cancel(self):
        """T-02935 New Method : To cancel the order if partner is blacklisted"""
        # T-03091: Upated to is_blacklisted to support archived blacklist records
        for order in self.filtered(lambda o: o.is_blacklisted and o.scayle_bind_ids):
            order.action_unlock()
            order.action_cancel()
        return True

    def action_create_and_validate_replacement_order(self):
        """T-02873 Action for Open the replacement order wizard"""
        self.ensure_one()
        # Validate creation of replacement orders if order is COD type.
        # T-03029 - Validate order if shipping carrier is 'home_cod' type.
        if self.eshop_cod or self.carrier_id.shipment_options == "home_cod":
            raise ValidationError(
                _(
                    "Replacement orders cannot be created for COD "
                    "(Cash on Delivery) orders."
                )
            )
        return {
            "name": _("Replacement Order"),
            "type": "ir.actions.act_window",
            "res_model": "replacement.order",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_order_id": self.id},
        }

    def action_open_scayle_cancellation_wizard(self):
        """#T-03065 New method : Added for eShop cancellation wizard"""
        self.ensure_one()
        if not (
            self.env.is_admin() or self.env.is_superuser()
        ) and not self.env.user.has_group("connector_scayle.group_eshop_cancellation"):
            raise AccessError(_("You are not allowed to cancel Scayle orders."))
        scayle_lines = self.env["scayle.sale.order.line"].search(
            [
                ("odoo_id", "in", self.order_line.ids),
            ]
        )
        cancelable_lines = scayle_lines.filtered(lambda line: not line.cancel_in_odoo)
        if not cancelable_lines:
            raise UserError(_("There are no products left to cancel."))
        return {
            "name": "Scayle Lines",
            "type": "ir.actions.act_window",
            "res_model": "scayle.sale.order.line",
            "view_mode": "tree",
            "domain": [
                ("id", "in", cancelable_lines.ids),
            ],
            "target": "new",
            "context": {
                "group_by": "product_id",
            },
        }

    def get_refund_domain(self):
        """#T-03104 New method : for refund domain"""
        domain = [
            ("odoo_id", "in", self.order_line.ids),
            ("shipment_created", "=", True),
            ("return_created", "=", False),
            ("return_sync_to_scayle", "=", False),
            ("stock_return_move_id", "=", False),
            ("forced_return", "=", False),
        ]
        return domain

    def action_open_refund_the_return_wizard(self):
        """#T-03104 New method: To open refund the return wizard"""
        self.ensure_one()
        # T-3104 access error if no group found for user
        if not (
            self.env.is_admin() or self.env.is_superuser()
        ) and not self.env.user.has_group(
            "connector_scayle.group_eshop_refund_for_return"
        ):
            raise AccessError(_("You are not allowed to refund products to Scayle."))
        # T-03104 get refund domain
        refund_domain = self.get_refund_domain()
        # T-03104 Get lines to refund to scayle
        refundable_lines = self.env["scayle.sale.order.line"].search(
            refund_domain,
            order="id",
        )
        # T-03104 get allowed scayle lines dict with moves
        allowed_scayle_lines = self.get_refundable_scayle_lines(
            refundable_lines=refundable_lines
        )
        # T-03104 extract scayle lines to add in domain
        allowed_line_ids = [line.id for line in allowed_scayle_lines]
        return {
            "name": "Scayle Lines To Refund",
            "type": "ir.actions.act_window",
            "res_model": "scayle.sale.order.line",
            "view_mode": "tree",
            "view_id": self.env.ref("connector_scayle.view_scayle_refund_line_tree").id,
            "domain": [
                ("id", "in", allowed_line_ids),
            ],
            "target": "new",
            "context": {
                "group_by": "product_id",
            },
        }

    def get_refundable_scayle_lines(self, refundable_lines):
        """#T-03104 New method : Return refundable Scayle lines mapped to their
        related stock move."""
        # build refundable mapping of scayle binds and stock moves
        refundable_mapping = {}
        # T-03104 get refund domain
        refund_domain = self.get_refund_domain()
        # Filter refundable lines based on refund domain
        refundable_lines = refundable_lines.filtered_domain(refund_domain)
        lines_by_sale_line = refundable_lines.grouped("odoo_id")
        # T-03104 get the missing locations from the operation type
        for sale_line, scayle_lines in lines_by_sale_line.items():
            # T-03104 Find return moves lines associated with missing products
            missing_move_lines = sale_line.move_ids.mapped("move_line_ids").filtered(
                lambda moveline: moveline.move_id.state == "done"
                and moveline.picking_id.is_actual_return
                and moveline.picking_type_id.missing_location_ids
                and (
                    moveline.location_dest_id
                    in moveline.picking_type_id.missing_location_ids
                )
            )
            # Skip if no return moves lines are available from this sale line
            if not missing_move_lines:
                continue
            # Get already forced return lines to avoid over-processing quantity
            # in our flow 1 scayle_bind_ids is considered as 1 qty.
            # Case : if 1 sale order line have 2 qty so it will have 2 binds ids
            # so we can safely check the length based on number of scayle binds
            forced_qty = len(
                sale_line.scayle_bind_ids.filtered(lambda line: line.forced_return)
            )
            # Available quantity in current move lines quantity
            total_missing_qty = int(sum(missing_move_lines.mapped("quantity")))
            # check remaining qty from total missing qty.
            remaining_qty = total_missing_qty - forced_qty
            # Skip if no quantity left to process
            if remaining_qty <= 0:
                continue
            scayle_lines = scayle_lines[:remaining_qty]
            # T-03104 group move lines by move
            move_lines_by_move = missing_move_lines.grouped("move_id")
            for move, move_lines in move_lines_by_move.items():
                move_qty = int(sum(move_lines.mapped("quantity")))
                allowed_scayle_lines = scayle_lines[:move_qty]
                if not allowed_scayle_lines:
                    continue
                # Collect allowed lines for further processing
                scayle_lines -= allowed_scayle_lines
                # Store mapping between Scayle line and stock return move
                refundable_mapping.update({line: move for line in allowed_scayle_lines})
        # If no allowed lines found raise error.
        if not refundable_mapping:
            raise UserError(
                _("There are no missing products available for refund to Scayle.")
            )
        return refundable_mapping


class ScayleSaleOrder(models.Model):
    _name = "scayle.sale.order"
    _inherit = ["scayle.binding", "api.payload.history", "eshop.sale.order"]
    _inherits = {"sale.order": "odoo_id"}
    _description = "Scayle Sale Order"

    _rec_name = "name"

    odoo_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sale Order",
        required=True,
        ondelete="restrict",
    )

    order_reference_key = fields.Char()

    scayle_date_order = fields.Datetime(string="eShop Order Date")

    shop_id = fields.Char()

    country_code = fields.Char(string="Shop Country Code")

    shop_key = fields.Char()

    scayle_order_status = fields.Char(string="eShop Order Status")

    def action_open_in_scayle_panel(self):
        """#T-02353 Action for open scayle panel for the sale orders in new tab"""
        client_action = self.backend_id.get_url_scayle_panel(binding=self)
        return client_action


class ScayleOrderAdapter(Component):
    _name = "scayle.sale.order.adapter"
    _inherit = "scayle.adapter"
    _apply_on = "scayle.sale.order"

    _eshop_model = "orders"
    _eshop_model_cancel = "order-item-cancelled"
    _eshop_create_model = "create-shipment"

    def _get_external_ids_to_cancel(self, line_bindings):
        return line_bindings.filtered(
            lambda x: x.cancel_in_odoo and not x.cancel_sync_to_scayle
        ).mapped("external_id")

    def cancel(self, external_id, **kwargs):
        """Cancel a record on the external system"""
        order = kwargs.get("relation")
        shop_key = self.backend_record.shop_key
        country_code = self.backend_record.country_id.code
        # change from MR !1298
        order_item_ids = self._get_external_ids_to_cancel(
            order.mapped("order_line.scayle_bind_ids")
        )
        if not order_item_ids:
            raise MappingError(_("No Items found to cancel in scayle!"))
        items = []
        # Prepare the data to cancel order.
        for order_item in order_item_ids:
            order_item_id = self.backend_record.get_converted_external_id(order_item)
            items.append({"orderItemId": order_item_id})
        external_id = self.backend_record.get_converted_external_id(external_id)
        data_dict = {
            "orderId": external_id,
            "shopKey": shop_key,
            "countryCode": country_code,
            "items": items,
        }
        data = json.dumps(data_dict)
        result = self._call(
            resource_path=self._eshop_model_cancel, arguments=data, http_method="post"
        )

        # Store data while cancelling SO at remote # T-02320
        so_cancelled_binding = order.scayle_bind_ids.filtered(
            lambda binding: binding.external_id == external_id
            and binding.backend_id == self.backend_record
        )
        so_cancelled_binding.api_payload_data = data_dict
        return result


# Sale order line


class ScayleSaleOrderLine(models.Model):
    _name = "scayle.sale.order.line"
    _inherit = ["scayle.binding", "eshop.sale.order.line"]
    _description = "Scayle Sale Order Line"
    _inherits = {"sale.order.line": "odoo_id"}

    odoo_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale Order Line",
        required=True,
        ondelete="restrict",
    )
    backend_id = fields.Many2one(
        string="eShop Backend",
        readonly=True,
        store=True,
        # override 'scayle.binding', can't be INSERTed if True:
        required=False,
    )
    # T-02113 - Fields
    scayle_quantity = fields.Float(string="Product Quantity", copy=False)
    stock_shipment_move_id = fields.Many2one(
        comodel_name="stock.move", string="Stock Shipment Move", copy=False
    )
    stock_return_move_id = fields.Many2one(
        comodel_name="stock.move", string="Stock Return Move", copy=False
    )

    # T-02113 Fields - Cancel Items
    cancel_in_odoo = fields.Boolean(copy=False)
    cancel_sync_to_scayle = fields.Boolean(string="Cancel sync to eShop", copy=False)

    # T-02113 Fields - Create Shipment
    shipment_created = fields.Boolean(copy=False)
    shipment_sync_to_scayle = fields.Boolean(
        string="Shipment sync to eShop", copy=False
    )

    # T-02113 Fields - Create Return
    # Fields with copy=False are always False after duplication.
    return_created = fields.Boolean(copy=False)
    return_sync_to_scayle = fields.Boolean(string="Return sync to eShop", copy=False)

    # T-02313 Add warehouse reference key.
    warehouse_reference_key = fields.Char(
        string="eShop Warehouse Reference Key", copy=False
    )

    # T-02556 New Fields
    scayle_currency_id = fields.Many2one(
        related="odoo_id.order_id.eshop_currency_id", string="eShop Currency"
    )

    # T-02828 New fields to store relevent data for scalye report
    scayle_sub_item_info = fields.Json(
        name="Scayle SubItem Information", copy=False, readonly=True
    )
    scayle_product_name = fields.Char(
        name="Scayle Product Name", copy=False, readonly=True
    )
    frame_product_price = fields.Integer(
        name="Scayle Product Price", copy=False, readonly=True
    )
    with_rxlenstype = fields.Boolean(
        name="With RX Lenstype ", copy=False, readonly=True
    )
    # T-03104 Added field
    forced_return = fields.Boolean(copy=False)

    def action_cancel_selected_lines(self):
        """#T-03065 New Method: to cancel record in
        odoo and export cancel order to scayle"""
        if not self:
            raise ValidationError(_("Please select at least one line."))
        self.write({"cancel_in_odoo": True})
        lines = self.filtered(
            lambda line: line.cancel_in_odoo and not line.cancel_sync_to_scayle
        )
        if not lines:
            raise ValidationError(_("Nothing to export. All lines already synced."))
        orders = lines.mapped("order_id")
        for order in orders:
            order.with_context(auto_cancel=True).export_cancel_orders()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "sticky": False,
                "message": _("Selected lines cancelled and synced successfully."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_refund_selected_lines(self):
        """#T-03104 Refund selected products to Scayle from the binding lines.
        Case:
        - Scayle binding lines contain 3 refundable lines.
        - Missing picking also contains 3 similar product moves.
        - If the user selects only one line for a particular product from sale order,
          only the related Scayle binding line will be exported to Scayle for refund.
        """
        selected_binds = self
        if not selected_binds:
            raise ValidationError(_("Please select at least one line."))
        # T-03104 get refundable lines.
        allowed_scayle_lines = self.order_id.get_refundable_scayle_lines(
            refundable_lines=selected_binds
        )
        # T-03104 used to export pickings
        picking_scayle_lines = defaultdict(lambda: self.env[self._name])
        product_qty_mapping = defaultdict(int)
        # Update selected Scayle lines with related return move
        try:
            for line, move in allowed_scayle_lines.items():
                line.write(
                    {
                        "return_created": True,
                        "stock_return_move_id": move,
                        "forced_return": True,
                    }
                )
                product_qty_mapping[line.product_id] += 1
                picking_scayle_lines[move.picking_id] |= line
                # Remove successfully processed line
                selected_binds -= line
            # T-03104 add the pickings in loop
            for picking, scayle_lines in picking_scayle_lines.items():
                picking.export_return_items(scayle_return_lines=scayle_lines)
        except Exception as ex:
            raise ValidationError(
                _("An error occurred while processing the refund: %s") % str(ex)
            ) from ex
        # Make the chatter message and post
        product_details = "".join(
            f"<li>{html_escape(product.display_name)}| {qty}</li>"
            for product, qty in product_qty_mapping.items()
        )

        message = Markup(
            "The products have been forcefully marked for refund export to Scayle:"
            "<br/><br/>"
            "<b>Product | Qty</b>"
            f"<ul>{product_details}</ul>"
        )

        # Post the chatter message on the Sales Order
        sales_order = self.mapped("odoo_id.order_id")
        sales_order.message_post(body=message)
        if selected_binds:
            product_details_for_warning = ", ".join(
                selected_binds.mapped("product_id.display_name")
            )

            warning_message = (
                _(
                    "The following product(s) could not be included in the refund. "
                    "They were already processed or are ineligible: %s"
                )
                % product_details_for_warning
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "sticky": False,
                    "message": warning_message,
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "sticky": False,
                "message": _("Selected products are refunded to Scayle."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def calculate_subitem_total_price(self):
        """T-02828 New Method: return the total price of subitems"""
        total_price = sum(
            item.get("price", 0)
            for item in self.scayle_sub_item_info.get("subItems", [])
            if self.with_rxlenstype and self.scayle_sub_item_info
        )
        return total_price

    def get_rx_addition_info(self):
        """T-02828 New Method: return the rx addition info of subitems"""
        additional_info = []
        if not (self.scayle_sub_item_info and self.with_rxlenstype):
            raise ValidationError(_("Scayle Subitem Info/Rx Lenstype is not found."))
        for item in self.scayle_sub_item_info.get("subItems", []):
            info = ""
            # Check attributes for each item
            for attribute in item.get("attributes", []):
                if attribute["name"] != "rxAdditionalInfo":
                    continue
                # Get the value for de_DE
                info = attribute["value"].get("de_DE", "")
            if not info:
                continue
            additional_info.append(info)
        if not additional_info:
            raise ValidationError(_("Empty Scayle Subitem Info found"))
        return additional_info

    def get_rx_product_name(self):
        """#T-02828 New Method: Return the rx product name."""
        if not self.scayle_product_name:
            raise ValidationError(_("Scayle product name is not found"))
        return self.scayle_product_name

    def get_rx_product_price(self):
        """T-02828 New Method: return the rx product price"""
        return ((self.frame_product_price) / 100) or 0

    def get_scayle_line_tax(self, tax_percent, backend, price_include=False):
        """#T-02492 New method: Returns the tax which are exists in odoo."""
        if not tax_percent:
            return
        tax_percent = float(tax_percent)
        tax = self.env["account.tax"].search(
            [
                ("company_id", "=", backend.company_id.id),
                ("type_tax_use", "=", "sale"),
                ("amount", "=", tax_percent),
                ("price_include", "=", price_include),
            ],
            limit=1,
        )
        if not tax:
            _logger.warning(
                ("Tax doesn't exist in Odoo! for company {}, amount {}").format(
                    backend.company_id.name, tax_percent
                )
            )
        return tax

    def get_price_info_dict(self):
        """New Method: Added method to return price dict. # T-02515"""
        return {
            "price_without_tax": "priceWithoutTax",
            "price_with_tax": "price",
            "tax_amount": "taxAmount",
            "tax_rate": "tax",
        }

    def get_price_tax_mapping(self, item):
        """
        #T-02515 New Method: Returns the dictionary for mapping of price and tax
        fields for item.
        """
        convert_eshop_price_to_odoo = self.env[
            "sale.order.line"
        ].convert_eshop_price_to_odoo
        price_dict = {}
        price_info_dict = self.get_price_info_dict()
        for key, value in price_info_dict.items():
            if value not in item:
                raise MappingError(
                    _("%(value)s is not received from the order items!")
                    % {"value": value}
                )

            # setting 0 if key is present and empty values
            # ('',False, None etc...) received
            price = 0 if not item[value] else item[value]
            if key != "tax_rate":
                price = convert_eshop_price_to_odoo(price)
            price_dict[f"eshop_{key}"] = price
        return price_dict


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends("scayle_bind_ids", "scayle_bind_ids.shipment_sync_to_scayle")
    def _compute_shipment_status(self):
        """#T-02155 Add compute method to add the shipment status from scayle"""
        res = super()._compute_shipment_status()
        for line in self.filtered(lambda line: line.scayle_bind_ids):
            if all(
                line_bind.shipment_sync_to_scayle for line_bind in line.scayle_bind_ids
            ):
                line.eshop_shipment_status = "full_shipment"
            elif any(
                line_bind.shipment_sync_to_scayle for line_bind in line.scayle_bind_ids
            ):
                line.eshop_shipment_status = "partial_shipment"
            else:
                line.eshop_shipment_status = "no_shipment"
        return res

    @api.depends("scayle_bind_ids", "scayle_bind_ids.cancel_sync_to_scayle")
    def _compute_cancel_status(self):
        """#T-02113 Add compute method to add the cancel status from scayle."""
        res = super()._compute_cancel_status()
        for line in self.filtered(lambda line: line.scayle_bind_ids):
            if all(
                line_bind.cancel_sync_to_scayle for line_bind in line.scayle_bind_ids
            ):
                line.eshop_cancel_status = "cancelled"
            elif any(
                line_bind.cancel_sync_to_scayle for line_bind in line.scayle_bind_ids
            ):
                line.eshop_cancel_status = "partial_cancelled"
            else:
                line.eshop_cancel_status = "not_cancelled"
        return res

    @api.depends("scayle_bind_ids", "scayle_bind_ids.return_sync_to_scayle")
    def _compute_return_status(self):
        """#T-02155 Add compute method to add the return status from scayle."""
        res = super()._compute_return_status()
        for line in self.filtered(lambda line: line.scayle_bind_ids):
            if all(
                line_bind.return_sync_to_scayle for line_bind in line.scayle_bind_ids
            ):
                line.eshop_return_status = "full_return"
            elif any(
                line_bind.return_sync_to_scayle for line_bind in line.scayle_bind_ids
            ):
                line.eshop_return_status = "partial_return"
            else:
                line.eshop_return_status = "no_return"
        return res

    scayle_bind_ids = fields.One2many(
        comodel_name="scayle.sale.order.line",
        inverse_name="odoo_id",
        string="eShop Bindings",
        copy=False,
    )

    def write(self, vals):
        """# T-02873: Skip quantity validation when updating replacement orders."""
        if (
            self.scayle_bind_ids
            and "product_uom_qty" in vals
            and not self.env.context.get("update_replace_qty")
        ):
            raise ValidationError(_("Cannot Update Quantity"))
        return super().write(vals)

    def get_manufacturing_order(self):
        """T-02810: Method to get manufacturing order from sale order line"""
        self.ensure_one()
        return

    def get_fulfillment_moves(self):
        """T-02810: Method to get fulfillment moves from sale order line"""
        self.ensure_one()
        return False

    def _compute_current_status(self):
        """
        T-02810: Override Method to Set Sequential Status for SOL
        """
        for line in self:
            # Fetching required states and related records
            move_states = line.move_ids.filtered(
                lambda move: not move.origin_returned_move_id
            ).mapped("state")
            manufacturing_order = line.get_manufacturing_order()
            glass_product_move_available = None
            if manufacturing_order:
                glass_product_move_available = (
                    manufacturing_order.move_raw_ids.filtered(
                        lambda move: move.product_id.categ_id.is_glass
                    )
                )
            # Get fulfillment moves
            fulfillment_moves = line.get_fulfillment_moves()
            # Evaluate conditions and set current_status
            if not line.scayle_bind_ids:
                # Scayle Binding must be present
                line.current_status = False
            elif (
                # All lines are cancelled in Odoo
                all(bind.cancel_in_odoo for bind in line.scayle_bind_ids)
            ):
                line.current_status = "cancelled"
            elif (
                (
                    # Any Move is waiting or confirmed and no frame_product_id
                    any(state in ("waiting", "confirmed") for state in move_states)
                    and not line.frame_product_id
                )
                or (
                    # Manufacturing order exists but no glass product move available
                    manufacturing_order and not glass_product_move_available
                )
                or (
                    # Manufacturing order exists, reservation state not assigned,
                    # components availability state is late or unavailable,
                    # and glass product move available
                    manufacturing_order
                    and manufacturing_order.reservation_state != "assigned"
                    and manufacturing_order.components_availability_state
                    in ("late", "unavailable")
                    and glass_product_move_available
                )
                or (
                    # T-03043:  Manufacturing order in done state but if MLTP/MIX route
                    # is set then finished products will be consolidate in pick opration
                    any(state in ("waiting", "confirmed") for state in move_states)
                    and manufacturing_order
                    and manufacturing_order.state == "done"
                    and line.route_id.is_mltp_route
                )
            ):
                line.current_status = "waiting_for_product"
            elif (
                # Manufacturing order exists, reservation state not assigned,
                # components availability state is expected or available
                manufacturing_order
                and manufacturing_order.reservation_state != "assigned"
                and manufacturing_order.components_availability_state
                in ("expected", "available")
            ):
                line.current_status = "ready_for_production"
            elif (
                # Manufacturing order exists, reservation state is assigned or
                # components availability state is available
                manufacturing_order
                and (
                    manufacturing_order.reservation_state == "assigned"
                    or manufacturing_order.components_availability_state == "available"
                )
            ):
                line.current_status = "in_production"
            elif (
                # All Move are assigned and manufacturing order is done
                # or does not exist
                move_states
                and all(state == "assigned" for state in move_states)
                and (not manufacturing_order or manufacturing_order.state == "done")
            ):
                if fulfillment_moves:
                    line.current_status = "in_fulfillment"
                else:
                    line.current_status = "ready_for_delivery"
            elif (
                # All lines have return created
                all(bind.return_created for bind in line.scayle_bind_ids)
            ):
                line.current_status = "return"
            elif (
                # Any lines have return created
                any(bind.return_created for bind in line.scayle_bind_ids)
            ):
                line.current_status = "partial_return"
            elif (
                # All lines have shipment created and not return created
                all(
                    bind.shipment_created and not bind.return_created
                    for bind in line.scayle_bind_ids
                )
            ):
                line.current_status = "shipped"
            elif (
                # Any lines have shipment created and not return created
                any(
                    bind.shipment_created and not bind.return_created
                    for bind in line.scayle_bind_ids
                )
            ):
                line.current_status = "partial_shipped"
            else:
                # Default None of the above conditions are met
                line.current_status = False
