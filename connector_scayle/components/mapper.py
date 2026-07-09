from odoo.addons.component.core import AbstractComponent
from odoo.addons.connector.components.mapper import mapping


class ScayleImportMapper(AbstractComponent):
    _name = "scayle.import.mapper"
    _inherit = ["base.scayle.connector", "base.import.mapper"]
    _usage = "import.mapper"

    @mapping
    def api_payload_data(self, record):
        """#T-02320 Import api payload history"""
        if not self.env[self._apply_on]._fields.get("api_payload_data", False):
            return {}
        return {"api_payload_data": record}

    @mapping
    def backend_id(self, record):
        """Mapped the backend id"""
        return {"backend_id": self.backend_record.id}


class ScayleExportMapper(AbstractComponent):
    _name = "scayle.export.mapper"
    _inherit = ["base.scayle.connector", "base.export.mapper"]
    _usage = "export.mapper"
