import logging

from odoo import _

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping
from odoo.addons.connector.exception import MappingError
from odoo.addons.connector_settings.components.misc import to_iso_datetime

_logger = logging.getLogger(__name__)


class ScaylePickingReturnBatchExporter(Component):
    """Export picking for return."""

    _name = "scayle.picking.return.exporter"
    _inherit = "scayle.exporter"
    _apply_on = ["scayle.stock.picking.return"]
    _default_binding_field = "scayle_return_bind_ids"

    def _before_export(self):
        """
        Inherit Method: Added method to restrict export return to scayle for partial
        quantities for frame products. # T-02556
        """
        # we don't get anything in self.binding.odoo_id so used self.odoo_record
        if self.odoo_record.restrict_export_return_to_eshop:
            raise MappingError(
                _(
                    "The picking is restricted from export to scayle. Most likely the "
                    "return picking contains partial quantities for prescription "
                    "products, which is not supported."
                )
            )
        return super()._before_export()

    def update_return_to_scayle(self, picking):
        """New Method : [Added method to update status return at scayle]"""
        for move in picking.move_ids:
            for line_bind in move.sale_line_id.scayle_bind_ids:
                if (
                    move != line_bind.stock_return_move_id
                    or not line_bind.return_created
                    or line_bind.return_sync_to_scayle
                ):
                    continue
                line_bind.return_sync_to_scayle = True

    def _after_export(self, binding):
        binding.write({"external_id": binding.odoo_id.id})
        self.update_return_to_scayle(binding.odoo_id)
        # T-02320 Store the values that we're sending to the scayle
        if self.transform_data:
            binding.api_payload_data = self.transform_data
        return super()._after_export(binding)

    def run(self, binding, record=None, *args, **kwargs):
        """#T-02515 Method Inherit: To apply lock in dependency"""
        if record.sale_id:
            # T-02902 Added advisory lock based on sale order.
            record.get_advisory_lock_or_retry(sale_id=record.sale_id)
        return super().run(binding, record, *args, **kwargs)


class ScaylePickingReturnExporterMapper(Component):
    _name = "scayle.picking.return.export.mapper"
    _inherit = "scayle.export.mapper"
    _apply_on = "scayle.stock.picking.return"

    @mapping
    def return_items(self, record):
        """Mapped return_items"""
        return_items = []
        # Filter out the sample product moves to be exported to scayle
        for move in record.move_ids.filtered(lambda move: not move.is_sample_move):
            for line_bind in move.sale_line_id.scayle_bind_ids.filtered(
                lambda line: line.return_created and not line.return_sync_to_scayle
            ):
                if move != line_bind.stock_return_move_id:
                    continue
                return_key = "{}{}".format(
                    self.backend_record.return_prefix, line_bind.external_id
                )
                return_items.append(
                    {
                        "returnKey": return_key,
                        "received": to_iso_datetime(record.date, timezone=False),
                    }
                )
        if not return_items:
            raise MappingError(_("No return items found to export on scayle!"))
        return {"return_items": return_items}
