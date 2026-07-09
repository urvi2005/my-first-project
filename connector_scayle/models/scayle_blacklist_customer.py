from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BlacklistCustomerFilter(models.Model):
    _name = "blacklist.customer.filter"
    _description = "Blacklist Filter"
    _rec_name = "name"

    # T-02935 Added new fields
    name = fields.Char()
    domain = fields.Char(
        help="Domain used to filter Out Partners.",
    )
    active = fields.Boolean(default=True)
    # T-03107 added new fields
    domain_type = fields.Selection(
        [
            ("partner", "Partner"),
            ("product", "Product"),
        ],
        default="partner",
        required=True,
        help="Select the type on which the filter should be applied.",
    )
    # T-02935 Add unique constraint for name
    _sql_constraints = [
        (
            "blacklist_customer_filter_name_uniq",
            "unique(name)",
            "A Filter with Same Name already exists.",
        ),
    ]

    @api.constrains("domain")
    def check_domain_for_blacklist_customer(self):
        """#T-02966 Constrain Method: Check domain should not be empty"""
        for blacklist_filter in self:
            if not blacklist_filter.domain or blacklist_filter.domain == "[]":
                raise ValidationError(
                    _("At least one rule should be provided for blacklist filter.")
                )

    @api.onchange("domain_type")
    def _onchange_domain_type(self):
        """T-03107 : New method to update domain when domain type changes"""
        for blacklist_filter in self:
            blacklist_filter.domain = False
