import time

from odoo.tests.common import users

from .common import ScayleTestCases


class ScayleSWSLogic(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """#T-02463 super call"""
        super().setUpClass()
        cls.category = cls.env["product.category"].search([], limit=1)
        cls.vendor1 = cls.env.ref("base.res_partner_address_13")
        cls.vendor2 = cls.env.ref("base.res_partner_1")
        seller_ids = [
            (
                0,
                0,
                {
                    "partner_id": cls.vendor1.id,
                    "company_id": cls.company_id.id,
                    "price": 12,
                    "product_code": "123456",
                },
            ),
            (
                0,
                0,
                {
                    "partner_id": cls.vendor2.id,
                    "company_id": cls.company_id.id,
                    "price": 10,
                    "product_code": "123456",
                },
            ),
        ]
        cls.product_templ = cls.env["product.template"].create(
            {"name": "Test template 1", "seller_ids": seller_ids}
        )
        cls.product_1 = cls.env["product.product"].create(
            {
                "name": "Test 1",
                "eshop_sws_logic": "from_category",
            }
        )
        cls.product_2 = cls.env["product.product"].create(
            {
                "name": "Test 2",
                "eshop_sws_logic": "yes",
                "product_tmpl_id": cls.product_templ.id,
            }
        )
        # Added combination indices explicitly due to multivariants were created and
        # both variant's combination indices were same
        # so unique indices error was thrown T-02463
        cls.product_2.product_variant_ids[
            0
        ].combination_indices = "combination_indices_1"
        cls.product_2.product_variant_ids[
            1
        ].combination_indices = "combination_indices_2"

    @users("inventory_manager")
    def test_sws_logic_for_product_1(self):
        """Check SWS logic for product_1's sale start and end dates."""
        # T-02463 Added test case for is_orderable False for eshop_sws_logic as
        # from_category
        self.asserts_for_sws_logic(product_variant=self.product_1)

    def get_inventory_and_sws_date(self, product_variant):
        """
        New Method : [#T-02463 Added new method for getting old and new dates for sws
        and inventory]
        """
        stock_update_date_record_list = product_variant.mapped("stock_update_date_ids")
        sws_date = []
        inv_date = []
        for stock_update_date_record in stock_update_date_record_list:
            sws_date.append(stock_update_date_record.sws_update_date)
            inv_date.append(stock_update_date_record.inventory_update_date)
        return sws_date, inv_date

    @users("inventory_manager")
    def test_sws_from_category_is_orderable_True(self):
        """
        New Method : [#T-02463 Added test case for scayle sws logic as from_category
        and is_orderable is True]
        """
        old_sws_dates, old_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        time.sleep(1)
        self.product_2.write({"eshop_sws_logic": "from_category"})
        self.product_2.categ_id = self.category.id
        self.product_2.categ_id.eshop_sws = False
        self.asserts_for_sws_logic(
            product_variant=self.product_2,
            is_orderable=True,
        )
        self.product_2.categ_id.eshop_sws = True
        self.asserts_for_sws_logic(
            product_variant=self.product_2,
            eshop_sws=True,
            is_orderable=True,
        )
        new_sws_dates, new_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        for element in range(len(new_sws_dates)):
            self.inventory_sws_date_assertions(
                old_sws=old_sws_dates[element],
                new_sws=new_sws_dates[element],
                should_match=False,
            )

    @users("inventory_manager")
    def test_sws_logic_no_is_orderable_True(self):
        """
        New Method : [#T-02463 Added test case for eshop_sws_logic as no and
        is_orderable as True]
        """
        old_sws_dates, old_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        time.sleep(1)
        self.product_2.write({"eshop_sws_logic": "no"})
        self.asserts_for_sws_logic(
            product_variant=self.product_2,
            is_orderable=True,
        )
        new_sws_dates, new_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        for element in range(len(new_sws_dates)):
            self.inventory_sws_date_assertions(
                old_sws=old_sws_dates[element],
                new_sws=new_sws_dates[element],
                should_match=False,
            )

    @users("inventory_manager")
    def test_sws_logic_no_is_orderable_False(self):
        """
        New Method : [#T-02463 Added test case for eshop_sws_logic as no and
        is_orderable as False]
        """
        old_sws_dates, old_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        time.sleep(1)
        self.product_1.write({"eshop_sws_logic": "no"})
        self.asserts_for_sws_logic(
            product_variant=self.product_1,
            is_orderable=False,
        )
        new_sws_dates, new_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        for element in range(len(new_sws_dates)):
            self.inventory_sws_date_assertions(
                old_sws=old_sws_dates[element],
                new_sws=new_sws_dates[element],
                should_match=True,
            )

    @users("inventory_manager")
    def test_sws_logic_yes_is_orderable_False(self):
        """
        New Method : [#T-02463 Added test case for eshop_sws_logic as yes and
        is_orderable as False]
        """
        old_sws_dates, old_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        time.sleep(1)
        self.product_1.write({"eshop_sws_logic": "yes"})
        self.asserts_for_sws_logic(product_variant=self.product_1)
        new_sws_dates, new_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        for element in range(len(new_sws_dates)):
            self.inventory_sws_date_assertions(
                old_sws=old_sws_dates[element],
                new_sws=new_sws_dates[element],
                should_match=True,
            )

    @users("inventory_manager")
    def test_sws_remove_supplierinfo(self):
        """
        New Method: Added test cases to check for removing supplier from template
        and also update sws dates. # T-02660
        """
        old_sws_dates, old_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        time.sleep(1)
        self.product_2.write({"eshop_sws_logic": "yes"})
        self.asserts_for_sws_logic(
            product_variant=self.product_2, eshop_sws=True, is_orderable=True
        )
        self.product_2.seller_ids.unlink()
        self.asserts_for_sws_logic(product_variant=self.product_2)

        new_sws_dates, new_inv_dates = self.get_inventory_and_sws_date(self.product_2)
        for element in range(len(new_sws_dates)):
            self.inventory_sws_date_assertions(
                old_sws=old_sws_dates[element],
                new_sws=new_sws_dates[element],
                should_match=False,
            )
