import logging
import uuid
from contextlib import contextmanager
from io import StringIO

import requests
from mako.runtime import Context
from mako.template import Template

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.connector.exception import MappingError

from ...components.backend_adapter import ScayleAPI, ScayleLocation

_logger = logging.getLogger(__name__)

IMPORT_DELTA_BUFFER = 30  # seconds


class ScayleBackend(models.Model):
    _name = "scayle.backend"
    _description = "Scayle Backend"
    _inherit = "connector.ecommerce.backend"

    shop_key = fields.Char(copy=False)
    country_id = fields.Many2one("res.country", string="Country")
    version = fields.Selection(
        selection_add=[("v1", "v1"), ("v2", "v2")],
        default="v1",
        ondelete={"v1": "set default", "v2": "set default"},
        required=True,
    )
    sale_prefix = fields.Char(
        help="A prefix put before the name of imported sales orders.\n"
        "For instance, if the prefix is 'mag-', the sales "
        "order 100000692 in scayle, will be named 'mag-100000692' "
        "in Odoo.",
        copy=False,
    )
    warehouse_ids = fields.Many2many(
        comodel_name="stock.warehouse",
        string="Warehouse",
        required=True,
        help="Warehouse used to compute the stock quantities.",
    )
    default_lang_id = fields.Many2one(
        comodel_name="res.lang",
        string="Default Language",
        help="If a default language is selected, the records "
        "will be imported in the translation of this language.",
    )
    odoo_scayle_token = fields.Char(
        "Odoo Scayle Token",
        copy=False,
        related="backend_group_id.backend_group_access_token",
        store=True,
    )
    test_odoo_scayle_token = fields.Char(
        "Test Odoo Scayle Token",
        copy=False,
        related="backend_group_id.test_backend_group_access_token",
        store=True,
    )
    default_pricelist_id = fields.Many2one(
        "product.pricelist", string="Pricelist", required=True
    )
    # T-02845 Added new field
    sunglasses_product = fields.Many2one(
        comodel_name="product.product",
        help="If selected, the product will be updated with the"
        " frame product received from RX sale order.",
    )

    is_import_customer_ref = fields.Boolean()

    # T-02085 - New fields to add prefix in key
    return_prefix = fields.Char(default="RET-")

    stock_endpoint = fields.Boolean(
        default=True, help="Activate the stock update endpoint"
    )
    order_creation_endpoint = fields.Boolean(
        default=True,
        help="Activate the order creation endpoint",
    )
    return_valid_if_exists = fields.Boolean()
    # T-02402 Add new field
    shop_id = fields.Char(copy=False)
    code = fields.Char(
        related="country_id.code",
        comodel_name="scayle.backend",
        store=True,
    )

    # T-02441: Added field
    scayle_panel_url_test = fields.Text(
        string="Staging Panel URL",
        help="""Please add mako template for ex :
        https://fim-prev.panel.scayle.cloud/add-ons/customer#/orders/${order_id}/details""",  # noqa: B950
    )

    # T-02441: Added field
    scayle_panel_url_production = fields.Text(
        string="Production Panel URL",
        help="""Please add mako template for ex :
        https://fim-live.panel.scayle.cloud/shops/${shop_id}/orders/search/${order_id}/details""",  # noqa: B950
    )

    # T-02494: Added field
    is_phonenumber_required = fields.Boolean(
        string="Phone Number Required",
        help="Set True if Customer Phone Number is required.",
    )

    # T-02536 m2m to forward scayle payload into another instance
    scayle_url_ids = fields.Many2many(
        comodel_name="scayle.url",
        relation="scayle_backend_scayle_url_rel",
        column1="scayle_backend_id",
        column2="scayle_url_id",
        string="Scayle URLs",
        copy=False,
    )
    # T-02556
    # T-02963 remove required from python level as
    # already added at xml level
    scayle_shop_id = fields.Many2one(
        comodel_name="scayle.shop", string="eShop", copy=False
    )
    auto_confirm_order = fields.Boolean(string="Auto Confirm Sale Order", default=True)
    # Moved fields from connector_scayle_inter_company # T-02556.
    auto_export_shipments = fields.Boolean(
        string="Auto Export Shipment On Scayle", default=True
    )
    auto_export_cancel = fields.Boolean(
        string="Auto Export Cancel On Scayle", default=True
    )

    # T-02803 New field for 7senders
    senders7_order_url = fields.Char(string="7senders Order URL")
    senders7_language = fields.Char(string="7senders Language")

    allow_sample_products = fields.Boolean(
        string="Auto Add Sample Products",
        help="If True, the sample product functionality will be enabled.",
    )

    # T-02402 Added constraints for unique shop_id.
    _sql_constraints = [
        (
            "shop_id_uniq",
            "unique(shop_id)",
            "A backend with the same shop_id already exists",
        ),
        (
            "sale_prefix_uniq",
            "unique(sale_prefix)",
            "A backend with the same sale prefix already exists",
        ),
    ]

    def copy(self, default=None):
        """T-02963 Inherit Method : to add copy text"""
        default = dict(default or {})
        if self.name:
            default["name"] = f"{self.name} (Copy)"
        return super().copy(default)

    # Token
    def get_backend_token(self, domain=None):
        """Scheduled action to get Backend token"""
        backend_ids = self.search(domain or [])
        for backend_id in backend_ids:
            backend_id.get_token()

    def get_token(self):
        """Get the access token from API."""
        with self.work_on(self._name) as work:
            backend_adapter = work.component(usage="backend.adapter")
            token_dict = backend_adapter.get_token()
            token = token_dict.get("access_token")
            if self.test_mode:
                self.test_token = token
            else:
                self.token = token

    def generate_odoo_scayle_token(self):
        """Generate Stock endpoint Token"""
        for backend in self:
            token = str(uuid.uuid4())
            if backend.test_mode:
                backend.test_odoo_scayle_token = token
            else:
                backend.odoo_scayle_token = token

    def _check_validation_pricelist(self, record):
        pricelist_id = self.default_pricelist_id
        if not pricelist_id:
            raise MappingError(
                _("Pricelist was not found, Please configure at backend level")
            )
        return pricelist_id

    @contextmanager
    def work_on(self, model_name, **kwargs):
        """Add the work on for scayle."""
        self.ensure_one()
        location = self.location
        token = self.token
        version = self.version
        debug_mode = kwargs.get("debug_mode", self.debug_mode)
        if self.test_mode:
            token = self.test_token
            location = self.test_location
        scayle_location = ScayleLocation(
            location=location,
            token=token,
            version=version,
            test_mode=self.test_mode,
            debug_mode=debug_mode,
        )

        with ScayleAPI(scayle_location) as scayle_api:
            _super = super()
            # from the components we'll be able to do: self.work.scayle_api
            with _super.work_on(model_name, remote_api=scayle_api, **kwargs) as work:
                yield work

    def get_scayle_model(self, current_scayle_model):
        """#T-02441 Return _scayle_model for URL"""
        scayle_model = ""
        with self.work_on(current_scayle_model) as work:
            backend_adapter = work.component(usage="backend.adapter")
            scayle_model = backend_adapter._scayle_model
        return scayle_model

    @api.model
    def get_url_scayle_panel(self, binding, scayle_model=False):
        """#T-02441: Return Sacyle Panel URL"""
        backend = self
        binding.ensure_one()
        if not backend:
            backend = binding.backend_id
        backend.ensure_one()
        external_id = binding.external_id
        if not external_id:
            raise ValidationError(
                _("Please Add External ID for %(binding_name)s ")
                % {"binding_name": binding.name}
            )

        if not backend.test_mode:
            base_url = backend.scayle_panel_url_production
        else:
            base_url = backend.scayle_panel_url_test
        if not base_url:
            raise ValidationError(_("Please Add the Scayle Panel URL on the Backend!"))
        try:
            mytemplate = Template(base_url)
            buf = StringIO()
            if not backend.test_mode:
                ctx = Context(
                    buf,
                    shop_id=backend.shop_id,
                    order_id=external_id,
                )
            else:
                ctx = Context(buf, order_id=external_id)
            mytemplate.render_context(ctx)
            url = buf.getvalue()
            client_action = {
                "type": "ir.actions.act_url",
                "target": "new",
                "url": url,
            }
            return client_action
        except Exception as ex:
            _logger.error(_("Error while calculating mako scayle panel URL: %s") % ex)

    @api.model
    def check_shipping_delivery_cost(self, applied_fees):
        """
        #T-02515 New Method: To raise mapping error if any other options
        is in the appliedFees except for 'deliveryCosts' or 'deliveryCosts found
        multiple times
        """
        # Method use: in delegation as we don't want to generate mapping error
        if not len(applied_fees):
            return
        elif (
            len(applied_fees) != 1
            or applied_fees[0].get("option", "") != "deliveryCosts"
        ):
            return _(
                "Only 1 entry of option 'deliveryCosts' is supported in appliedFees."
            )

    def get_shipping_cost(self, record, should_check=False):
        """
        New Method: Added method to return shipping cost with sum of amounts needed as
        shipping cost and also tax amount and if other than shipping cost found then
        raise error.

        TODO: Need to discuss if any shipping cost has different tax or not. And also
        need to discuss regarding needed to add different line for shipping line or
        just to sum up as per now we are doing sum up all required amount.
        """
        self.ensure_one()
        cost_dict = record.get("cost", {})
        if "appliedFees" not in cost_dict:
            return {}
        applied_fees = cost_dict.get("appliedFees", [])
        # Boolean, in case we want to generate mapping error, to maintain code
        # flexibility
        if should_check:
            message = self.check_shipping_delivery_cost(applied_fees)
            if message:
                raise MappingError(message)
        applied_fees = applied_fees[0]
        return {
            "withoutTax": applied_fees.get("amount", {}).get("withoutTax", 0),
            "withTax": applied_fees.get("amount", {}).get("withTax", 0),
            "tax_amount": applied_fees.get("tax", {}).get("vat", {}).get("amount", 0),
            "tax_rate": applied_fees.get("tax", {}).get("vat", {}).get("rate", 0.0),
        }

    @api.model
    def forward_data_to_scayle_url(self, url, data):
        """Forward the data to Scayle URLs"""
        if not url or not data:
            return
        headers = {
            "Content-Type": "application/json",
        }
        # pylint: disable=E8106
        requests.post(
            url,
            json=data,
            headers=headers,
        )
        # T-02767 - Added a timeout to handle error where  server takes long to respond.
        _logger.info("Payload is forwarded to URL %s", url)

    @api.model
    def get_converted_external_id(self, external_id):
        """
        #T-02666 New/Generic Method: To convert the external_id into integer if
        possible.
        """
        try:
            return int(external_id)
        except Exception:
            return external_id

    # change from MR !1298
    @api.model
    def _cron_export_remaining_sale_orders(self, domain=None):
        """#T-02668: Cron to export remaining cancel sale orders"""
        backends = self.search(domain or [])
        for backend in backends:
            partial_order_cancel = (
                self.env["scayle.sale.order.line"]
                .search(
                    [
                        ("cancel_in_odoo", "=", True),
                        ("cancel_sync_to_scayle", "=", False),
                        ("backend_id", "=", backend.id),
                    ]
                )
                .mapped("odoo_id.order_id")
            )
            for order in partial_order_cancel:
                order.with_context(auto_cancel=True).export_cancel_orders()

    # TODO: Remove me once stock_return_move_id has set to all the previous records
    @api.model
    def update_stock_return_moves(self, limit=None, offset=0):
        """
        #T-02767 New Method: Method to set stock_return_move_id for old records
        """
        domain = [("return_created", "=", True), ("stock_return_move_id", "=", False)]
        order_lines = self.env["scayle.sale.order.line"].search(
            domain, limit=limit, offset=offset
        )
        for order_line in order_lines.mapped("odoo_id"):
            returned_moves = order_line.move_ids.filtered(
                lambda m: m.origin_returned_move_id
                and m.picking_type_id.code == "incoming"
                and m.state == "done"
            )
            for move in returned_moves:
                to_return_qty = move.quantity
                sale_line_bindings = move.sale_line_id.scayle_bind_ids
                returned_bindings = sale_line_bindings.filtered(
                    lambda line: line.return_created
                    and not line.stock_return_move_id
                    and line.shipment_sync_to_scayle
                )
                if not returned_bindings or to_return_qty > len(returned_bindings):
                    continue
                unreturned_bindings = returned_bindings[: int(to_return_qty)]
                unreturned_bindings.write({"stock_return_move_id": move.id})

    @api.model
    def refused_order_delegation(self, message, external_id):
        """#T-02852 New Method: Failed queue job message"""
        description = (
            f"Scayle order delegation for {external_id} refused for the "
            f"following reason:\n'{message}'\n"
            "This job only serves as info and should be set to Done."
        )
        raise ValueError(description)
