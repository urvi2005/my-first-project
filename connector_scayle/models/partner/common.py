import logging
from datetime import timedelta
from hashlib import blake2b
from operator import attrgetter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    scayle_backend_id = fields.Many2one(
        string="Scayle Backend", comodel_name="scayle.backend"
    )
    scayle_bind_ids = fields.One2many(
        comodel_name="scayle.address",
        inverse_name="odoo_id",
        string="Scayle Bindings",
        copy=False,
    )

    @classmethod
    def _address_hash_fields(cls):
        """
        New Method: T-02816: Add class property for allowed field for the
        regenerate hash
        rtype: dict
        """
        return [
            "city",
            "country_id",
            "email",
            "lang",
            "name",
            "parcel_locker",
            "phone",
            "street",
            "street2",
            "type",
            "zip",
        ]

    @api.model
    def _generate_address_hash(self, address_values):
        """#T-02816 New Method: generate hash from received values"""
        address_hash = blake2b()
        address_fields = self._address_hash_fields()
        for field in address_fields:
            if field not in address_values:
                raise ValidationError(
                    _("field %(field)s not found in address value %(address_values)s")
                    % {"field": field, "address_values": address_values}
                )
            if isinstance(address_values, dict):
                field_value = address_values.get(field, "")
            else:
                if self.sudo().env["scayle.address"]._fields[field].type == "many2one":
                    field = f"{field}.id"
                field_value = attrgetter(field)(address_values) or ""
            address_hash.update(str(field_value).encode("UTF-8"))
        hash_id = address_hash.hexdigest()
        return hash_id

    @api.model
    def _cron_archive_customers(self, limit=50000):
        """#T-02818 Scheduled action: To archieve customers based on order days"""
        # Retrieve the configured number of days
        days_to_archive = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("archive_customer.order_days", 365)  # Default to 365 days
        )
        cutoff_date = fields.Datetime.now() - timedelta(days=days_to_archive)

        # T-02818 SQL query to fetch customers to archive
        # T-03091:changed from IN ('sale','done') to exclude only cancelled orders
        query = """
            SELECT rp.id, rp.name
            FROM res_partner rp
            LEFT JOIN sale_order so ON rp.id = so.partner_shipping_id
                AND so.date_order >= %s
                AND so.state NOT IN ('cancel')
            LEFT JOIN res_users ru ON rp.id = ru.partner_id
            LEFT JOIN scayle_address sa ON sa.odoo_id = rp.id
            WHERE rp.branch_code IS NULL
                AND so.id IS NULL
                AND ru.id IS NULL
                AND sa.id IS NOT NULL
            LIMIT %s
        """
        self.env.cr.execute(
            query, (cutoff_date, limit)
        )  # T-02818 - dynamic searching based on cutoff-date and limit
        customer_ids = [row[0] for row in self.env.cr.fetchall()]

        # T-02818 Archive the fetched customers
        if customer_ids:
            self.env["res.partner"].browse(customer_ids).write({"active": False})

    def write(self, vals):
        """#T-02816 Inherit Method: To raise validation if partner information modified
        based on certain condition"""
        is_restrict_partner = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("restrict_partner_address.by_all")
        ) or False
        if not is_restrict_partner:
            return super().write(vals)
        for partner in self:
            allowed_keys = set(self._address_hash_fields())
            if (
                partner.sudo().scayle_bind_ids
                and not self.env.user.has_group("connector.group_connector_manager")
                and allowed_keys.intersection(vals.keys())
            ):
                raise ValidationError(
                    _(
                        "Only Connector Managers can modify partner information "
                        "bound to Scayle."
                    )
                )
        return super().write(vals)


class ScayleAddress(models.Model):
    _name = "scayle.address"
    _inherit = ["scayle.binding", "eshop.res.partner"]
    _inherits = {"res.partner": "odoo_id"}
    _description = "Scayle Address"

    _rec_name = "backend_id"

    odoo_id = fields.Many2one(
        comodel_name="res.partner", string="Partner", required=True, ondelete="restrict"
    )

    _sql_constraints = [
        (
            "odoo_uniq",
            "unique(backend_id, odoo_id)",
            "A partner address can only have one binding by backend.",
        ),
    ]

    # Update
    backend_id = fields.Many2one(
        comodel_name="scayle.backend",
        string="Backend",
        store=True,
        readonly=True,
        required=False,
    )

    # !1311: Moved from res.partner T-02668
    scayle_partner_key = fields.Char()
    # !1311: Added Fields T-02556, # Moved from res.partner T-02668
    scayle_parent_id = fields.Char(string="Scayle Parent")

    # T-02816 Override the field to make it compute
    address_hash_code = fields.Char(
        string="Hash code for address",
        compute="_compute_address_hash_code",
        store=True,
    )

    allowed_partner_hash_fields = ResPartner._address_hash_fields()

    @api.depends(*allowed_partner_hash_fields)
    def _compute_address_hash_code(self):
        """
        #T-02816 Compute Method: To compute the hash if any hash fields are changed
        """
        ResPartner = self.env["res.partner"]
        for scayle_address in self:
            scayle_address.address_hash_code = ResPartner._generate_address_hash(
                scayle_address
            )
