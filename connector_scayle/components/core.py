from odoo.addons.component.core import AbstractComponent


class BaseScayleConnectorComponent(AbstractComponent):
    """
    Base scayle Connector Component
    All components of this connector should inherit from it.
    """

    _name = "base.scayle.connector"
    _inherit = "base.connector"
    _collection = "scayle.backend"
