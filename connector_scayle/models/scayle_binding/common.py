from odoo import api, fields, models


class ScayleBinding(models.AbstractModel):
    """
    Abstract Model for the Bindings.

    All the models used as bindings between scayle and Odoo
    (``scayle.res.partner``, ``scayle.product.template``, ...) should
    ``_inherit`` it.
    """

    _name = "scayle.binding"
    _inherit = "external.binding"
    _description = "Scayle Binding (abstract)"

    # odoo_id = odoo-side id must be declared in concrete model
    backend_id = fields.Many2one(
        comodel_name="scayle.backend",
        string="Scayle Backend",
        required=True,
        ondelete="restrict",
    )
    # fields.Char because 0 is a valid scayle ID
    external_id = fields.Char(string="ID on Scayle")

    created_at = fields.Datetime("Created At (on Scayle)")
    updated_at = fields.Datetime("Updated At (on Scaye)")

    def init(self):
        """#T-02360 Unique index for Backend ID and External ID"""
        if self._table == "scayle_binding":
            return
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS {}_unique_backend_external_id ON {}"
            " (external_id, backend_id) WHERE external_id IS NOT NULL and"
            " external_id != '' and external_id != 'False' and "
            "external_id != 'false'".format(self._table, self._table)
        )

    def get_paging_limit(self):
        """Method to return limit for one page"""
        # TODO discuss with paul based on binding or generic configuration?
        return 100

    @api.model
    def import_batch(self, backend, filters=None):
        """Batch Import"""
        if filters is None:
            filters = {}
        if "limit" not in filters:
            filters["limit"] = self.get_paging_limit()
        with backend.work_on(self._name) as work:
            importer = work.component(usage="batch.importer")
            return importer.run(filters=filters)

    @api.model
    def import_record(self, backend, external_id, force=False, data=None):
        """Import Record"""
        with backend.work_on(self._name) as work:
            importer = work.component(usage="record.importer")
            return importer.run(external_id, force=force, data=data)

    @api.model
    def export_batch(self, backend, filters=None):
        """Export Batch"""
        if filters is None:
            filters = {}
        with backend.work_on(self._name) as work:
            exporter = work.component(usage="batch.exporter")
            return exporter.run(filters=filters)

    def export_record(self, backend, record, fields=None):
        """Export Record"""
        record.ensure_one()
        with backend.work_on(self._name) as work:
            exporter = work.component(usage="record.exporter")
            return exporter.run(self, record, fields)

    def export_delete_record(self, backend, external_id, **kwargs):
        """Delete a record on scayle"""
        with backend.work_on(self._name) as work:
            deleter = work.component(usage="record.exporter.deleter")
            return deleter.run(external_id, **kwargs)

    def export_cancel_record(self, backend, external_id, **kwargs):
        """Cancel a record on scayle"""
        with backend.work_on(self._name) as work:
            canceller = work.component(usage="record.canceller")
            return canceller.run(external_id, **kwargs)
