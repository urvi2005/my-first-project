from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ScayleShop(models.Model):
    _name = "scayle.shop"
    _description = "Store the information for scayle shop"

    name = fields.Char(required=True)
    sales_team_id = fields.Many2one(
        comodel_name="crm.team", string="Sales Team", copy=False, required=True
    )
    # T-02946 Added new fields
    za_enable = fields.Boolean()
    za_branch_partner_id = fields.Many2one(
        "res.partner",
        string="ZA Branch Partner",
        domain="[('branch_code', '!=', False),('is_intercompany', '!=', False)]",
        help="Select the ZA branch partner.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        copy=False,
        ondelete="restrict",
        domain="[('branch_code', '!=', False)]",
        required=True,
    )

    # T-02965 New field
    kls_tax_id = fields.Many2one(
        comodel_name="account.tax",
        copy=False,
        ondelete="restrict",
        help="If no tax amount received, then consider the configured percentage.",
    )

    # T-03084 New fields
    is_prevent_quick_reimbursement = fields.Boolean(
        help="If True, The Return will be verified before proceeding for quick "
        "reimbursement."
    )
    threshold_return_amount = fields.Float(
        help="Block the return auto reimbursement in case the threshold amount"
        " reached.",
        default=200.00,
    )
    ecommerce_categ_ids = fields.Many2many(
        comodel_name="ecommerce.category",
        relation="ecommerce_category_scayle_shop_rel",
        column1="scayle_shop_id",
        column2="ecommerce_category_id",
        string="Ecommerce Categories",
        help="Block the return auto reimbursement in case the product is from"
        " configured category.",
    )

    @api.constrains("threshold_return_amount")
    def _check_threshold_return_amount(self):
        """T-03084 Constrain Method: Raise validation if the threshold is negative"""
        for scayle_shop in self.filtered(
            lambda shop: shop.threshold_return_amount < 0.0
        ):
            raise ValidationError(
                _(
                    "The Threshold Return Amount must not be negative in %s.",
                    scayle_shop.name,
                )
            )

    # Added sql constraints for duplicate record creation. # T-02556
    _sql_constraints = [
        (
            "sales_team_id_partner_id_unique",
            "unique (sales_team_id, partner_id)",
            "You cannot have Scayle Shop with same Customer and Sales Team.",
        )
    ]
