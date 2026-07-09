import time
from datetime import timedelta

from odoo.tests import common
from odoo.tests.common import users

from .common import ScayleTestCases


@common.tagged("post_install", "-at_install")
class ScayleStockUpdateTestCases(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """#T-02331 product configuration"""
        super().setUpClass()

    @users("sale_manager")
    def test_from_date_gt_to_date_response(self):
        """#T-02331 Method to cover the empty response"""
        # T-02331 No response expected if from_date is higher than to_date
        from_date = self.from_date + timedelta(days=1)
        to_date = self.from_date - timedelta(days=1)
        multi_wh_multi_prod = self.get_payload_for_webhook(
            warehouses=self.wh_ref_keys,
            products=self.product_skus,
            from_date=from_date,
            to_date=to_date,
        )
        response_1 = self.process_stock_update_webhook(multi_wh_multi_prod)
        self.check_no_response_assertions(response=response_1)

        single_wh_multi_prod = self.get_payload_for_webhook(
            warehouses=[self.wh1.warehouse_reference_key],
            products=self.product_skus,
            from_date=from_date,
            to_date=to_date,
        )
        response_2 = self.process_stock_update_webhook(single_wh_multi_prod)
        self.check_no_response_assertions(response=response_2)

        single_wh_single_prod = self.get_payload_for_webhook(
            warehouses=[self.wh1.warehouse_reference_key],
            products=[self.test_product_1.default_code],
            from_date=from_date,
            to_date=to_date,
        )
        response_3 = self.process_stock_update_webhook(single_wh_single_prod)
        self.check_no_response_assertions(response=response_3)

        multi_wh_single_prod = self.get_payload_for_webhook(
            warehouses=self.wh_ref_keys,
            products=[self.test_product_2.default_code],
            from_date=from_date,
            to_date=to_date,
        )
        response_4 = self.process_stock_update_webhook(multi_wh_single_prod)
        self.check_no_response_assertions(response=response_4)

        from_date = self.from_date - timedelta(days=2)
        to_date = self.from_date + timedelta(days=2)

        no_from_date_payload = self.get_payload_for_webhook(
            warehouses=self.wh_ref_keys,
            to_date=to_date,
        )
        no_from_date_reponse = self.process_stock_update_webhook(no_from_date_payload)
        self.check_product_quant_and_inventory_date_webhook(
            response=no_from_date_reponse, record_count=3
        )

        no_to_date_payload = self.get_payload_for_webhook(
            warehouses=self.wh_ref_keys,
            from_date=from_date,
        )
        no_to_date_reponse = self.process_stock_update_webhook(no_to_date_payload)
        self.check_product_quant_and_inventory_date_webhook(
            response=no_to_date_reponse, record_count=3
        )

    @users("admin")
    def test_inventory_date_for_pickings(self):
        """#T-02331 Method to increase the quantity through incoming"""
        self.check_quant_and_inventory_date_from_receipt(
            {
                self.test_product_1.default_code: {
                    "demand_qty": 5,
                    "expected_qty": 5,
                },
                self.test_product_2.default_code: {
                    "demand_qty": 5,
                    "expected_qty": 5,
                },
            }
        )
        # T-02331 Method to increase the quantity through outgoing
        self.check_quant_and_inventory_date_from_delivery(
            {
                self.test_product_1.default_code: {
                    "demand_qty": 2,
                    "expected_qty": 3,
                },
                self.test_product_2.default_code: {
                    "demand_qty": 2,
                    "expected_qty": 3,
                },
            }
        )
        stock_update_1_wh_1 = self.test_product_1.stock_update_date_ids.filtered(
            lambda st: st.warehouse_id == self.wh1
        )
        stock_update_1_wh_2 = self.test_product_1.stock_update_date_ids.filtered(
            lambda st: st.warehouse_id == self.wh2
        )
        inventory_date_1 = stock_update_1_wh_1.inventory_update_date
        inventory_date_2 = stock_update_1_wh_2.inventory_update_date

        # T-02331 code to update the inventory date through scrap
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh1.out_type_id.id,
                "location_id": self.wh1.lot_stock_id.id,
                "location_dest_id": self.wh2.lot_stock_id.id,
                "state": "draft",
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.test_product_1.id,
                            "product_uom": self.test_product_1.uom_id.id,
                            "location_id": self.wh1.lot_stock_id.id,
                            "location_dest_id": self.wh2.lot_stock_id.id,
                            "name": self.test_product_1.name,
                            "product_uom_qty": 2,
                            "quantity": 2,
                        },
                    )
                ],
            }
        )

        picking.action_assign()
        picking.button_validate()
        # Compute will trigger and check the inventory date needs to be updated
        self.test_product_1.stock_quant_ids.flush_recordset()
        scrap = self.env["stock.scrap"].create(
            {
                "picking_id": picking.id,
                "product_id": self.test_product_1.id,
                "product_uom_id": self.test_product_1.uom_id.id,
                "scrap_qty": 1,
            }
        )
        time.sleep(1)
        scrap.action_validate()
        new_inventory_date_1 = stock_update_1_wh_1.inventory_update_date
        new_inventory_date_2 = stock_update_1_wh_2.inventory_update_date
        self.inventory_sws_date_assertions(
            old_inv=inventory_date_1,
            new_inv=new_inventory_date_1,
        )
        self.inventory_sws_date_assertions(
            old_inv=inventory_date_2,
            new_inv=new_inventory_date_2,
        )

        single_wh_single_prod = self.get_payload_for_webhook(
            warehouses=[self.wh1.warehouse_reference_key],
            products=[self.test_product_1.default_code],
            from_date=self.from_date - timedelta(days=1),
            to_date=self.to_date + timedelta(days=1),
        )
        response = self.process_stock_update_webhook(single_wh_single_prod)
        quantity_dict = {
            self.test_product_1.default_code: 1,
        }
        self.check_product_quant_and_inventory_date_webhook(
            response=response,
            quantity_dict=quantity_dict,
            warehouses=[self.wh1],
            products=[self.test_product_1.default_code],
            record_count=1,
        )

    @users("inventory_manager")
    def test_internal_transfer(self):
        """
        #T-02331 Method to make sure that the inventory update date is not updated
        in the internal transfer
        """
        inventory_update_date_old_wh_1 = (
            self.test_product_1.stock_update_date_ids.filtered(
                lambda su: su.warehouse_id == self.wh1
            ).mapped("inventory_update_date")
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh1.int_type_id.id,
                "location_id": self.env.ref("stock.stock_location_customers").id,
                "location_dest_id": self.env.ref("stock.stock_location_suppliers").id,
                "state": "draft",
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.test_product_1.id,
                            "product_uom": self.test_product_1.uom_id.id,
                            "name": self.test_product_1.name,
                            "product_uom_qty": 2,
                            "location_id": self.env.ref(
                                "stock.stock_location_customers"
                            ).id,
                            "location_dest_id": self.env.ref(
                                "stock.stock_location_suppliers"
                            ).id,
                            "quantity": 2,
                        },
                    )
                ],
            }
        )
        time.sleep(1)
        picking.button_validate()
        inventory_update_date_new_wh_1 = (
            self.test_product_1.stock_update_date_ids.filtered(
                lambda su: su.warehouse_id == self.wh1
            ).mapped("inventory_update_date")
        )
        self.inventory_sws_date_assertions(
            old_inv=inventory_update_date_old_wh_1[0],
            new_inv=inventory_update_date_new_wh_1[0],
            should_match=True,
        )
