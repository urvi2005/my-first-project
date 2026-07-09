import logging

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping
from odoo.addons.connector.exception import MappingError

_logger = logging.getLogger(__name__)


class AddressImportMapper(Component):
    _name = "scayle.address.import.mapper"
    _inherit = "scayle.import.mapper"
    _apply_on = "scayle.address"

    @mapping
    def name(self, record):
        """Mapped name."""
        name = record.get("firstName") or ""
        if record.get("lastName"):
            name += " %s" % (record.get("lastName"))
        return {"name": name}

    @mapping
    def street(self, record):
        """Mapped street."""
        # T-02862 Mapped street with collection point
        address = record.get("cp_address")
        if address:
            return {"street": address}
        return {"street": record.get("streetHouseNumber")}

    @mapping
    def street2(self, record):
        """Mapped street2."""
        # T-02862 Mapped street2 with collection point
        customer_key = record.get("cp_customer_number")
        if customer_key:
            return {"street2": customer_key}
        return {"street2": record.get("additional")}

    @mapping
    def city(self, record):
        """Mapped city."""
        return {"city": record.get("city")}

    @mapping
    def country(self, record):
        """Mapped country."""
        country_id = self.env["res.country"].search(
            [("code", "=", record.get("countryCode"))],
            limit=1,
        )
        return {"country_id": country_id.id if country_id else ""}

    @mapping
    def zip(self, record):
        """Mapped zip."""
        return {"zip": record.get("zipCode")}

    @mapping
    def type(self, record):
        """Mapped type."""
        # Hardcoded for delivery type as now we are only mapping for shipping address.
        # T-02556
        return {"type": "delivery"}

    @mapping
    def lang(self, record):
        """Mapped lang."""
        lang_id = self.backend_record.default_lang_id
        return {"lang": lang_id.code if lang_id else ""}

    @mapping
    def parcel_locker(self, record):
        """Mapped parcel_locker."""
        record = record.get("collectionPoint") or {}
        parcel_locker = record.get("type")
        return {"parcel_locker": parcel_locker or ""}

    @mapping
    def phone(self, record):
        """Mapped phone."""
        phone = record.get("phoneNumber")
        return {"phone": phone or ""}

    def finalize(self, map_record, values):
        """
        #T-02816 Inherit Method: raise error if the mapping fields and
        hash generation fields are mismatched
        """
        values = super().finalize(map_record=map_record, values=values)
        allowed_hash_fields = self.env["res.partner"]._address_hash_fields()
        source_keys = values.keys()
        # Check if every source key is allowed
        invalid_keys = [
            key
            for key in source_keys
            if key not in ["backend_id"] and key not in allowed_hash_fields
        ]

        if invalid_keys:
            raise MappingError(
                f"The following keys are not allowed: {invalid_keys}. "
                f"As it is not set in Allowed keys to generate hash which are: "
                f"{allowed_hash_fields}"
            )

        return values
