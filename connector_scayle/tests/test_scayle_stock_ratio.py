from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests.common import tagged, users

from .common import ScayleTestCases


@tagged("post_install", "-at_install")
class ScayleStockRatioTests(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """
        T-02583 Method Inherit: Setup method to add extra configuration for
        scayle stock ratio
        """
        super().setUpClass()

        cls.product_to_distribute_quant = cls.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "product",
                "default_code": "SCAYLE-STOCK-RATIO",
                "categ_id": cls.product_category.id,
            }
        )

    def create_quant_for_distributed_product(
        self, quantity, inventory_quantity=None, product=None
    ):
        """
        #T-02583 New Method: Create the stock quant to check the quantities are
        properly distributed or not.
        """
        product = product or self.product_to_distribute_quant
        self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.wh1.lot_stock_id.id,
                "quantity": quantity,
                "inventory_quantity": inventory_quantity or quantity,
            }
        )

    def create_quant_for_distributed_product_for_wh2(
        self, quantity, inventory_quantity=None, product=None
    ):
        """
        T-02849 New Method: Create the stock quant to check the quantities are
        properly distributed or not for WH2.
        """
        product = product or self.product_to_distribute_quant
        self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.wh2.lot_stock_id.id,
                "quantity": quantity,
                "inventory_quantity": inventory_quantity or quantity,
            }
        )

    @users("connector_sale_inventory_manager")
    def test_invalid_configuration_assertion(self):
        """
        #T-02583 New Method: Make sure that the fields value
        are configured properly.
        """
        with self.assertRaises(ValidationError):
            self.scayle_ratio1.percentage = 99

    @users("connector_sale_inventory_manager")
    def test_sellable_qty_without_distribution(self):
        """#T-02583 New Method: Normal Calculation of Sellable Quantity."""
        product = self.product_to_distribute_quant
        self.set_distribution_percentage(magento_percentage=20, scayle_percentage=80)
        self.create_quant_for_distributed_product(quantity=50)
        self.check_sellable_quantity(40, product.default_code)
        # T-02849 To check sellable quantity without distribution for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(40, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_sellable_qty(self):
        """#T-02583 New Method: Normal Calculation of Sellable Quantity."""
        # T-02863 create branded product and product_brand_ratio.
        self.brand_product = self.env["product.brand"].create(
            {
                "name": "Branded Product",
            }
        )
        product = self.product_to_distribute_quant
        self.set_distribution_percentage(
            magento_percentage=23,
            scayle_percentage=52,
        )
        self.assertTrue(
            product.categ_id.eshop_stock_ratio_ids, "Scayle Stock ratio not updated"
        )
        # T-02863 check with eshop stock ratios.
        self.create_quant_for_distributed_product(quantity=50)
        self.check_sellable_quantity(26, product.default_code)
        self.check_sellable_quantity_for_unified_warehouse(26, product.default_code)
        # T02863 Update product brand id.
        product.product_brand_id = self.brand_product
        # T-2863 after updating product brand , check sellable quantity.
        # The scayle ratio should be created with is 52, so qty = 26.
        self.check_sellable_quantity(26, product.default_code)
        # T-02863 Update Branded product Ratio.
        self.set_distribution_percentage(
            magento_percentage=23,
            scayle_percentage=22,
            branded_product=self.brand_product,
        )
        self.assertTrue(
            product.categ_id.eshop_brand_ratio_ids,
            "Scayle Product Brand ratio not updated",
        )
        # T-02863 check sellable quantity after brand update.
        self.check_sellable_quantity(11, product.default_code)
        # T-02863 To check sellable quantity without distribution for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(11, product.default_code)

    @users("connector_sale_inventory_manager")
    def test_sellable_qty_with_distribution(self):
        """
        #T-02583 New Method: Quantity distribution of Sellable Quantity.
        40*(17%) = 6, 40(83%) = 33, one quantity remains, it goes to the ratio, which
        has highest percentage , so the quantity would be (in this method) = 33 +1
        """
        product = self.product_to_distribute_quant
        self.create_quant_for_distributed_product(quantity=40)
        self.set_distribution_percentage(magento_percentage=17, scayle_percentage=83)
        self.check_sellable_quantity(34, product.default_code)
        # T-02849 To check sellable quantity with distribution for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(34, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_sellable_qty_with_no_distribution(self):
        """
        #T-02583 New Method: Quantity distribution of Sellable Quantity.
        40*(17%) = 6, 40(83%) = 33, one quantity remains, it goes to the ratio, which
        has highest percentage , so the quantity would be (in this method) = 6
        """
        product = self.product_to_distribute_quant
        self.create_quant_for_distributed_product(quantity=40)
        self.set_distribution_percentage(magento_percentage=83, scayle_percentage=17)
        self.check_sellable_quantity(6, product.default_code)
        # T-02849 To check sellable quantity with no distribution for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(6, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_low_calculated_qty(self):
        """
        #T-02583 New Method: To Make sure that the sellable quantity should be returned
         based on the calculation, even if the calculated quantity is less than the
        threshold quantity
        """
        product = self.product_to_distribute_quant
        self.create_quant_for_distributed_product(quantity=30)
        self.set_distribution_percentage(magento_percentage=90, scayle_percentage=10)
        self.check_sellable_quantity(3, product.default_code)
        # T-02849 To check low calculated quantity for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(3, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_high_threshold_qty_with_no_backend(self):
        """
        #T-02583 New Method: Returns the product sellable quantity, as it is lower than
        the threshold qty of category.
        """
        product = self.product_to_distribute_quant
        self.set_distribution_percentage(magento_percentage=10, scayle_percentage=90)
        self.create_quant_for_distributed_product(quantity=4)
        self.check_sellable_quantity(4, product.default_code)
        # T-02849 To check high threshold quantity with no backend for unified warehouse
        self.check_sellable_quantity_for_unified_warehouse(4, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_high_threshold_qty_with_backend(self):
        """
        #T-02583 New Method: Returns the product sellable quantity, as it is lower than
        the threshold qty of category.
        """
        self.set_distribution_percentage(magento_percentage=90, scayle_percentage=10)
        product = self.product_to_distribute_quant
        self.create_quant_for_distributed_product(quantity=4)
        self.check_sellable_quantity(0, product.default_code)
        # T-02849 To check high threshold quantity with backend for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(0.0, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_secure_max_buffer_with_backend(self):
        """
        #T-02583 New Method: Returns the product sellable quantity, as it is lower than
        the threshold qty of category.
        """
        self.set_distribution_percentage(magento_percentage=20, scayle_percentage=70)
        product = self.product_to_distribute_quant
        self.create_quant_for_distributed_product(quantity=500)
        self.check_sellable_quantity(350, product.default_code)
        # T-02849 To check secure max buffer with backend for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(350, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_secure_max_buffer_with_distribution(self):
        """
        #T-02583 New Method: Returns the product sellable quantity, as it is lower than
        the threshold qty of category.
        """
        self.set_distribution_percentage(magento_percentage=7, scayle_percentage=83)
        product = self.product_to_distribute_quant
        self.create_quant_for_distributed_product(quantity=67)
        self.check_sellable_quantity(56, product.default_code)
        # T-02849 To check secure max buffer with distribution for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(56, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_primary_stock_ratio_with_no_percentage(self):
        """
        #T-02583 New Method: Don't get the scayle stock ratio if the percentage is 0,
        # It always have the 0 value.
        """
        self.set_distribution_percentage(magento_percentage=30, scayle_percentage=0)
        product = self.product_to_distribute_quant
        self.create_quant_for_distributed_product(quantity=100)
        self.check_sellable_quantity(0, product.default_code)
        # T-02849 To check primary stock ratio with nopercentage for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(0.0, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_secondary_stock_ratio_with_no_percentage(self):
        """
        #T-02583 New Method: If the matched scayle ratio having percentage.
        # Assign all the sellable quantities by excluding security_max_buffer
        """
        product_category = self.env["product.category"].create(
            {"name": "Test Category", "security_max_buffer": 20}
        )
        product = self.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "product",
                "default_code": "TEST-SCAYLE-STOCK-RATIO-1",
                "categ_id": product_category.id,
            }
        )
        self.set_distribution_percentage(
            magento_percentage=0,
            scayle_percentage=30,
            product_category=product_category,
        )
        self.create_quant_for_distributed_product(quantity=100, product=product)
        self.check_sellable_quantity(80, product.default_code)
        # T-02849 To check secondary stock ratio with no percentage for unified
        # warehouse.
        self.check_sellable_quantity_for_unified_warehouse(80, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_small_qty_with_less_percentage(self):
        """
        #T-02583 New Method: Ensure that the calculation is precise with the less
        qty.
        """
        product_category = self.env["product.category"].create(
            {"name": "Test Category", "security_max_buffer": 2}
        )
        product = self.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "product",
                "default_code": "TEST-SCAYLE-STOCK-RATIO-1",
                "categ_id": product_category.id,
            }
        )
        self.set_distribution_percentage(
            magento_percentage=50,
            scayle_percentage=50,
            product_category=product_category,
        )
        self.create_quant_for_distributed_product(quantity=5, product=product)
        self.check_sellable_quantity(2, product.default_code)
        # T-02849 To check small quantity with less percentage for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(2, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_small_qty_with_high_percentage(self):
        """
        #T-02583 New Method: Ensure that the calculation is precise with the less
        qty.
        """
        product_category = self.env["product.category"].create(
            {"name": "Test Category", "security_max_buffer": 2}
        )
        product = self.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "product",
                "default_code": "TEST-SCAYLE-STOCK-RATIO-1",
                "categ_id": product_category.id,
            }
        )
        self.set_distribution_percentage(
            magento_percentage=40,
            scayle_percentage=50,
            product_category=product_category,
        )
        self.create_quant_for_distributed_product(quantity=5, product=product)
        self.check_sellable_quantity(2, product.default_code)
        # T-02849 To check small quantity with high percentage for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(2, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_secure_max_buffer_with_even_distribution(self):
        """
        #T-02583 New Method: Ensure that the calculation is precise with the less
        qty in even distribution (max_buffer + security quantity).
        """
        product_category = self.env["product.category"].create(
            {"name": "Test Category", "security_max_buffer": 2}
        )
        product = self.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "product",
                "default_code": "TEST-SCAYLE-STOCK-RATIO-1",
                "categ_id": product_category.id,
            }
        )
        self.set_distribution_percentage(
            magento_percentage=7,
            scayle_percentage=83,
            product_category=product_category,
        )
        self.create_quant_for_distributed_product(quantity=67, product=product)
        self.check_sellable_quantity(58, product.default_code)
        # T-02849 To check secure max buffer with even distribution for unified
        # warehouse.
        self.check_sellable_quantity_for_unified_warehouse(58, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_bulk_percentages_high_scayle_low_magento(self):
        """#T-02583 Test to check cases in bulk"""
        total_qty_list = [
            {"magento_qty": 0, "scayle_qty": 1, "total_qty": 1},
            {"magento_qty": 0, "scayle_qty": 1, "total_qty": 2},
            {"magento_qty": 0, "scayle_qty": 2, "total_qty": 3},
            {"magento_qty": 1, "scayle_qty": 2, "total_qty": 4},
            {"magento_qty": 1, "scayle_qty": 3, "total_qty": 5},
            {"magento_qty": 1, "scayle_qty": 4, "total_qty": 6},
            {"magento_qty": 2, "scayle_qty": 4, "total_qty": 7},
            {"magento_qty": 2, "scayle_qty": 5, "total_qty": 8},
            {"magento_qty": 2, "scayle_qty": 6, "total_qty": 9},
            {"magento_qty": 3, "scayle_qty": 6, "total_qty": 10},
            {"magento_qty": 3, "scayle_qty": 6, "total_qty": 11},
            {"magento_qty": 3, "scayle_qty": 7, "total_qty": 12},
            {"magento_qty": 3, "scayle_qty": 8, "total_qty": 13},
            {"magento_qty": 4, "scayle_qty": 8, "total_qty": 14},
            {"magento_qty": 4, "scayle_qty": 9, "total_qty": 15},
            {"magento_qty": 4, "scayle_qty": 10, "total_qty": 16},
            {"magento_qty": 5, "scayle_qty": 10, "total_qty": 17},
            {"magento_qty": 5, "scayle_qty": 11, "total_qty": 18},
            {"magento_qty": 5, "scayle_qty": 12, "total_qty": 19},
            {"magento_qty": 6, "scayle_qty": 12, "total_qty": 20},
            {"magento_qty": 6, "scayle_qty": 12, "total_qty": 21},
            {"magento_qty": 6, "scayle_qty": 13, "total_qty": 22},
            {"magento_qty": 6, "scayle_qty": 14, "total_qty": 23},
            {"magento_qty": 7, "scayle_qty": 14, "total_qty": 24},
            {"magento_qty": 7, "scayle_qty": 15, "total_qty": 25},
            {"magento_qty": 7, "scayle_qty": 16, "total_qty": 26},
            {"magento_qty": 8, "scayle_qty": 16, "total_qty": 27},
            {"magento_qty": 8, "scayle_qty": 17, "total_qty": 28},
            {"magento_qty": 8, "scayle_qty": 18, "total_qty": 29},
            {"magento_qty": 9, "scayle_qty": 18, "total_qty": 30},
        ]
        product_category = self.env["product.category"].create(
            {"name": "Test Category"}
        )
        self.set_distribution_percentage(
            magento_percentage=30,
            scayle_percentage=60,
            product_category=product_category,
        )
        for i, calc_dict in enumerate(total_qty_list):
            product = self.env["product.product"].create(
                {
                    "name": "Test Product 1",
                    "type": "product",
                    "default_code": "TEST-SCAYLE-STOCK-RATIO-1 %s" % i,
                    "categ_id": product_category.id,
                }
            )
            self.create_quant_for_distributed_product(
                quantity=calc_dict["total_qty"], product=product
            )
            self.check_sellable_quantity(calc_dict["scayle_qty"], product.default_code)
            self.check_sellable_quantity_for_unified_warehouse(
                calc_dict["scayle_qty"], product.default_code
            )
            self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_bulk_percentages_low_scayle_high_magento(self):
        """#T-02583 Test to check cases in bulk"""
        total_qty_list = [
            {"scayle_qty": 0, "magento_qty": 1, "total_qty": 1},
            {"scayle_qty": 0, "magento_qty": 1, "total_qty": 2},
            {"scayle_qty": 0, "magento_qty": 2, "total_qty": 3},
            {"scayle_qty": 1, "magento_qty": 2, "total_qty": 4},
            {"scayle_qty": 1, "magento_qty": 3, "total_qty": 5},
            {"scayle_qty": 1, "magento_qty": 4, "total_qty": 6},
            {"scayle_qty": 2, "magento_qty": 4, "total_qty": 7},
            {"scayle_qty": 2, "magento_qty": 5, "total_qty": 8},
            {"scayle_qty": 2, "magento_qty": 6, "total_qty": 9},
            {"scayle_qty": 3, "magento_qty": 6, "total_qty": 10},
            {"scayle_qty": 3, "magento_qty": 6, "total_qty": 11},
            {"scayle_qty": 3, "magento_qty": 7, "total_qty": 12},
            {"scayle_qty": 3, "magento_qty": 8, "total_qty": 13},
            {"scayle_qty": 4, "magento_qty": 8, "total_qty": 14},
            {"scayle_qty": 4, "magento_qty": 9, "total_qty": 15},
            {"scayle_qty": 4, "magento_qty": 10, "total_qty": 16},
            {"scayle_qty": 5, "magento_qty": 10, "total_qty": 17},
            {"scayle_qty": 5, "magento_qty": 11, "total_qty": 18},
            {"scayle_qty": 5, "magento_qty": 12, "total_qty": 19},
            {"scayle_qty": 6, "magento_qty": 12, "total_qty": 20},
            {"scayle_qty": 6, "magento_qty": 12, "total_qty": 21},
            {"scayle_qty": 6, "magento_qty": 13, "total_qty": 22},
            {"scayle_qty": 6, "magento_qty": 14, "total_qty": 23},
            {"scayle_qty": 7, "magento_qty": 14, "total_qty": 24},
            {"scayle_qty": 7, "magento_qty": 15, "total_qty": 25},
            {"scayle_qty": 7, "magento_qty": 16, "total_qty": 26},
            {"scayle_qty": 8, "magento_qty": 16, "total_qty": 27},
            {"scayle_qty": 8, "magento_qty": 17, "total_qty": 28},
            {"scayle_qty": 8, "magento_qty": 18, "total_qty": 29},
            {"scayle_qty": 9, "magento_qty": 18, "total_qty": 30},
        ]
        product_category = self.env["product.category"].create(
            {"name": "Test Category"}
        )
        self.set_distribution_percentage(
            magento_percentage=60,
            scayle_percentage=30,
            product_category=product_category,
        )
        for i, calc_dict in enumerate(total_qty_list):
            product = self.env["product.product"].create(
                {
                    "name": "Test Product 1",
                    "type": "product",
                    "default_code": "TEST-SCAYLE-STOCK-RATIO-1 %s" % i,
                    "categ_id": product_category.id,
                }
            )
            self.create_quant_for_distributed_product(
                quantity=calc_dict["total_qty"], product=product
            )
            self.check_sellable_quantity(calc_dict["scayle_qty"], product.default_code)

    @users("connector_sale_inventory_manager")
    def test_secure_max_buffer_with_single_qty(self):
        """
        #T-02583 New Method: Ensure that the calculation is precise with the
        exception case(single qty) with max_buffer.
        """
        product_category = self.env["product.category"].create(
            {"name": "Test Category", "security_max_buffer": 1}
        )
        product = self.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "product",
                "default_code": "TEST-SCAYLE-STOCK-RATIO-1",
                "categ_id": product_category.id,
            }
        )
        self.set_distribution_percentage(
            magento_percentage=30,
            scayle_percentage=60,
            product_category=product_category,
        )
        self.create_quant_for_distributed_product(quantity=1, product=product)
        self.check_sellable_quantity(1, product.default_code)
        # T-02849 To check secure max buffer with single quantity for unified warehouse.
        self.check_sellable_quantity_for_unified_warehouse(1, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_no_secure_max_buffer_with_single_qty(self):
        """
        #T-02583 New Method: Ensure that the calculation is precise without the
        exception case(single qty) with max_buffer.
        """
        # For creation of
        product_category = self.env["product.category"].create(
            {"name": "Test Category"}
        )
        product = self.env["product.product"].create(
            {
                "name": "Test Product 1",
                "type": "product",
                "default_code": "TEST-SCAYLE-STOCK-RATIO-1",
                "categ_id": product_category.id,
            }
        )
        self.set_distribution_percentage(
            magento_percentage=30,
            scayle_percentage=60,
            product_category=product_category,
        )
        self.create_quant_for_distributed_product(quantity=1, product=product)
        self.check_sellable_quantity(1, product.default_code)
        # T-02849 To check no secure max buffer with single quantity for unified
        # warehouse.
        self.check_sellable_quantity_for_unified_warehouse(1, product.default_code)
        self.check_no_unified_key_in_request(product.default_code)

    @users("connector_sale_inventory_manager")
    def test_check_security_percentage(self):
        """New/Test Method: #T-02583 Check valid percentages"""
        product_category = self.env["product.category"].create(
            {"name": "Test Category"}
        )
        self.assertEqual(product_category.security_percentage, 0)
        self.set_distribution_percentage(
            magento_percentage=30,
            scayle_percentage=60,
            product_category=product_category,
        )
        self.assertEqual(product_category.security_percentage, 10)
        product_category.eshop_stock_ratio_ids[0].percentage = 25.5
        self.assertEqual(product_category.security_percentage, 14.5)
        product_category.eshop_stock_ratio_ids[0].percentage = 0.0
        product_category.eshop_stock_ratio_ids[1].percentage = 0.0
        self.assertEqual(product_category.security_percentage, 0)

    @users("connector_sale_inventory_manager")
    def test_sellable_qty_without_stock_ratio(self):
        """New/Test Method: #T-02849 To check quantity without stock ratio"""
        self.product_category_no_ratio = self.env["product.category"].create(
            {
                "name": "Category with no Stock Ratios",
                "eshop_skip_inventory_update": False,
            }
        )
        self.product_no_ratio = self.env["product.product"].create(
            {
                "name": "Test Product with No Stock Ratio",
                "type": "product",
                "default_code": "SCAYLE-STOCK-NO-RATIO",
                "categ_id": self.product_category_no_ratio.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": self.product_no_ratio.id,
                "location_id": self.wh1.lot_stock_id.id,
                "quantity": 100.0,
            }
        )
        # T-02849 To check sellable quantity without stock ratio for unified
        # warehouse.
        self.check_sellable_quantity_for_unified_warehouse(
            100.0, self.product_no_ratio.default_code
        )
        self.env["stock.quant"].create(
            {
                "product_id": self.product_no_ratio.id,
                "location_id": self.wh2.lot_stock_id.id,
                "quantity": 50.0,
            }
        )
        self.check_sellable_quantity_for_unified_warehouse(
            150, self.product_no_ratio.default_code
        )

    @users("connector_sale_inventory_manager")
    def test_no_sku_send_in_request(self):
        """New/Test Method: #T-02849 To test no SKU send in request of stock-update"""
        self.create_quant_for_distributed_product(quantity=50)
        self.check_no_product_sku_in_request(50, "SCAYLE-STOCK-RATIO")

    @users("connector_sale_inventory_manager")
    def test_from_date_condition(self):
        """
        New/Test Method: #T-02849 Test the condition where from_date is set and the
        stock update dates should be greater than or equal to from_date.
        """
        from_date = datetime(2025, 3, 1)
        self.create_quant_for_distributed_product_for_wh2(quantity=50)
        self.create_quant_for_distributed_product(quantity=100)
        self.check_from_date_condition(from_date, 150, "SCAYLE-STOCK-RATIO")

    @users("connector_sale_inventory_manager")
    def test_to_date_condition(self):
        """
        New/Test Method: #T-02849 Test the condition where to_date is set and the stock
        update dates should be less than or equal to to_date.
        """
        to_date = datetime(2030, 3, 5)
        self.create_quant_for_distributed_product_for_wh2(quantity=50)
        self.create_quant_for_distributed_product(quantity=100)
        self.check_to_date_condition(to_date, 150, "SCAYLE-STOCK-RATIO")
