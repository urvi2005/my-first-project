import logging

from odoo import _

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping
from odoo.addons.connector.exception import MappingError
from odoo.addons.connector_settings.components.misc import to_iso_datetime

_logger = logging.getLogger(__name__)


class ScayleSaleOrderBatchExporter(Component):
    """Export Sale order for fulfillment."""

    _name = "scayle.sale.order.exporter"
    _inherit = "scayle.exporter"
    _apply_on = ["scayle.sale.order"]

    def update_sync_shipment_on_order(self, picking):
        """New Method : [Added method to update status shipment at scayle]"""
        for move in picking.move_ids:
            for line_bind in move.sale_line_id.scayle_bind_ids:
                if (
                    move != line_bind.stock_shipment_move_id
                    or not line_bind.shipment_created
                    or line_bind.shipment_sync_to_scayle
                ):
                    continue
                line_bind.shipment_sync_to_scayle = True

    def run(self, binding, record=None, *args, **kwargs):
        """
        Override Method to create the shipment for each picking
        with sale binding.
        """
        if not binding:
            return _("Sale order is not linked with scayle.")
        if binding.eshop_shipment_status == "full_shipment":
            return _(
                "The shipment is already sync to scayle for sale order %s."
                % (binding.name)
            )
        picking_ids = binding.picking_ids.filtered(
            lambda p: p.sale_id
            and p.picking_type_id.code == "outgoing"
            and not p.sync_full_shipment_picking_scayle
            and p.state == "done"
            and not p.sync_return_picking_scayle
            and p.sale_id.eshop_shipment_status in ["partial_shipment", "no_shipment"]
        )
        if not picking_ids:
            return _("There is no picking yet done for sale order %s ") % (
                binding.external_id
            )
        self.transform_data = {}
        for picking in picking_ids:
            move_ids = picking._validate_move_scayle()
            if not move_ids:
                continue
            map_record = self.mapper.map_record(picking)
            data = self._create_data(map_record)
            if not data:
                return _("Nothing to export.")
            self._create(data)
            # Added transform data to store data while exporting at
            # component level # T-02320
            self.transform_data.update(data)
            self.update_sync_shipment_on_order(picking)
        self._after_export(binding)

    def _after_export(self, binding):
        """
        Inherit Method : [# T-02320 Inherit method for storing data in
        api_payload_data while exporting]
        """
        if self.transform_data:
            binding.api_payload_data = self.transform_data
        return super()._after_export(binding)


class ScayleSaleOrderExporterMapper(Component):
    _name = "scayle.sale.order.export.mapper"
    _inherit = "scayle.export.mapper"
    _apply_on = "scayle.sale.order"

    @mapping
    def orderId(self, record):
        """Mapped orderId"""
        if not record:
            raise MappingError(_("No picking record found to create shipment."))
        order_id = self.backend_record.get_converted_external_id(
            record.sale_id.scayle_order_id
        )
        return {"orderId": order_id}

    @mapping
    def shopKey(self, record):
        """Mapped shopKey"""
        shopKey = self.backend_record.shop_key
        return {"shopKey": shopKey}

    @mapping
    def countryCode(self, record):
        """Mapped countryCode"""
        countryCode = self.backend_record.country_id.code
        return {"countryCode": countryCode}

    @mapping
    def carrier(self, record):
        """Mapped carrier"""
        if not record.sale_id.carrier_id.eshop_carrier_code:
            raise MappingError(
                _("There is no shipping carrier code in delivery carrier.")
            )
        return {"carrier": record.sale_id.carrier_id.eshop_carrier_code}

    @mapping
    def items(self, record):
        """Mapped items"""
        if not record:
            raise MappingError(_("No Record found to export!"))
        line_items = []
        # Filter out the sample product moves to be exported to scayle
        for move in record.move_ids.filtered(lambda move: not move.is_sample_move):
            for line_bind in move.sale_line_id.scayle_bind_ids:
                if (
                    move != line_bind.stock_shipment_move_id
                    or not line_bind.shipment_created
                    or line_bind.shipment_sync_to_scayle
                ):
                    continue
                return_key = "{}{}".format(
                    self.backend_record.return_prefix, line_bind.external_id
                )
                order_item_id = self.backend_record.get_converted_external_id(
                    line_bind.external_id
                )
                line_items.append(
                    {"orderItemId": order_item_id, "returnKey": return_key}
                )
        if not line_items:
            raise MappingError(_("No shipment items found to export on scayle!"))
        return {"items": line_items}

    @mapping
    def deliveryDate(self, record):
        """Mapped deliveryDate"""
        if not record.sale_id.effective_date:
            raise MappingError(
                _("There is no effective_date in order %(order_name)s")
                % {"order_name": record.sale_id.name}
            )

        return {
            "deliveryDate": to_iso_datetime(
                record.sale_id.effective_date, timezone=True
            )
        }

    @mapping
    def shipmentKey(self, record):
        """Add the carrier tracking ref without everstox."""
        if not record.carrier_tracking_ref:
            raise MappingError(
                _("There is no carrier tracking ref set in picking %(picking_name)s")
                % {"picking_name": record.name}
            )

        shipment_key = f"{record.carrier_tracking_ref}"
        return {"shipmentKey": shipment_key}

    @mapping
    def returnIdentCode(self, record):
        """Mapped returnIdentCode"""
        return_ident_code = "{}{}".format(
            self.backend_record.return_prefix, record.sale_id.scayle_order_id
        )
        return {"returnIdentCode": return_ident_code}
