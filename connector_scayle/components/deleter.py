from odoo.addons.component.core import AbstractComponent


class ScayleDeleter(AbstractComponent):
    """Base deleter for scayle"""

    _name = "scayle.exporter.deleter"
    _inherit = "base.ecommerce.exporter.deleter"
    _usage = "record.exporter.deleter"
