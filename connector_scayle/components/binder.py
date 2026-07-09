from odoo.addons.component.core import Component


class ScayleModelBinder(Component):
    """
    Bind records and give odoo/scayle ids correspondence

    Binding models are models called ``scayle.{normal_model}``,
    like ``scayle.product.product``.
    They are ``_inherits`` of the normal models and contains
    the scayle ID, the ID of the scayle Backend and the additional
    fields belonging to the scayle instance.
    """

    _name = "scayle.binder"
    _inherit = ["base.binder", "base.scayle.connector"]
    _apply_on = [
        "scayle.sale.order",
        "scayle.address",  # ADD: T-02726
        "scayle.stock.picking.return",
    ]
