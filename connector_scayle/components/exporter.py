"""

Exporters for Scayle.

In addition to its export job, an exporter has to:

* check in scayle if the record has been updated more recently than the
  last sync date and if yes, delay an import
* call the ``bind`` method of the binder to update the last sync date

"""

import logging

from odoo.addons.component.core import AbstractComponent

_logger = logging.getLogger(__name__)


class ScayleExporter(AbstractComponent):
    """A common flow for the exports to scayle"""

    _name = "scayle.exporter"
    _inherit = ["base.ecommerce.exporter", "base.scayle.connector"]
    _usage = "record.exporter"
    _default_binding_field = "scayle_bind_ids"


class ScayleBatchExporter(AbstractComponent):
    _name = "scayle.batch.exporter"
    _inherit = "base.ecommerce.batch.exporter"
    _usage = "batch.exporter"


class ScayleDirectBatchExporter(AbstractComponent):
    _name = "scayle.direct.batch.exporter"
    _inherit = ["scayle.batch.exporter", "base.ecommerce.direct.batch.exporter"]


class ScayleDelayedBatchExporter(AbstractComponent):
    """Delay export of the records"""

    _name = "scayle.delayed.batch.exporter"
    _inherit = [
        "scayle.batch.exporter",
        "base.ecommerce.delayed.batch.exporter",
    ]
