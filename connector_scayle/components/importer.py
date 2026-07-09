"""

Importers for Scayle.

An import can be skipped if the last sync date is more recent than
the last update in Scayle.

They should call the ``bind`` method if the binder even if the records
are already bound, to update the last sync date.

"""

import logging

from odoo.addons.component.core import AbstractComponent

_logger = logging.getLogger(__name__)


class ScayleImporter(AbstractComponent):
    """Base importer for scayle"""

    _name = "scayle.importer"
    _inherit = ["base.ecommerce.importer", "base.scayle.connector"]
    _usage = "record.importer"


class ScayleImportMapChild(AbstractComponent):
    """:py:class:`MapChild` for the Imports"""

    _name = "scayle.map.child.import"
    _inherit = ["base.scayle.connector", "base.map.child.import"]
    _usage = "import.map.child"


class ScayleBatchImporter(AbstractComponent):
    _name = "scayle.batch.importer"
    _inherit = "base.ecommerce.batch.importer"
    _usage = "batch.importer"


class ScayleDirectBatchImporter(AbstractComponent):
    _name = "scayle.direct.batch.importer"
    _inherit = ["scayle.batch.importer", "base.ecommerce.direct.batch.importer"]


class ScayleDelayedBatchImporter(AbstractComponent):
    _name = "scayle.delayed.batch.importer"
    _inherit = ["scayle.batch.importer", "base.ecommerce.delayed.batch.importer"]
