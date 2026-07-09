from odoo import fields, models


class SupplierInfo(models.Model):
    _inherit = "product.supplierinfo"

    # T-02463 currently we are not supporting the product_code to calculate the sws,
    # then we don't have to add inverse for it.

    # product_code = fields.Char(inverse="_inverse_recompute_sws")
    product_id = fields.Many2one(inverse="_inverse_recompute_sws")
    product_tmpl_id = fields.Many2one(inverse="_inverse_recompute_sws")
    company_id = fields.Many2one(inverse="_inverse_recompute_sws")

    def unlink(self):
        """
        #T-02425 We also have recompute sws when the seller ids is deleted
        from template
        """
        template_variants = self.mapped("product_tmpl_id.product_variant_ids")
        supplierinfo_variants = self.mapped("product_id")
        products = template_variants | supplierinfo_variants
        res = super().unlink()
        products._inverse_recompute_sws()
        return res

    def _inverse_recompute_sws(self):
        """#T-02425 Update the sws update date for company or product_code"""
        template_variants = self.mapped("product_tmpl_id.product_variant_ids")
        supplierinfo_variants = self.mapped("product_id")
        products = template_variants | supplierinfo_variants
        products._inverse_recompute_sws()
