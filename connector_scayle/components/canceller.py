from odoo.addons.component.core import AbstractComponent


class ScayleCanceller(AbstractComponent):
    """Base cancel for Scayle"""

    _name = "scayle.record.canceller"
    _inherit = "base.ecommerce.canceller"
    _usage = "record.canceller"
