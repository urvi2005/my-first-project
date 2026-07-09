import time
from datetime import timedelta

from odoo.tests.common import tagged, users

from .common import ScayleTestCases


@tagged("post_install", "-at_install")
class ScayleSWSTestCases(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """#T-02331 super call"""
        super().setUpClass()

    @users("connector_sale_inventory_manager")
    def test_product_stock_update_dates(self):
        """#T-02331 Test method to update the inventory date and sws update"""
        stock_update_ids = self.test_product_1.stock_update_date_ids
        self.assertEqual(len(stock_update_ids), 2)
        stock_update_ids_wh_1 = stock_update_ids.filtered(
            lambda su: su.warehouse_id == self.wh1
        )
        stock_update_ids_wh_2 = stock_update_ids.filtered(
            lambda su: su.warehouse_id == self.wh2
        )
        inventory_update_dates_wh1 = stock_update_ids_wh_1.inventory_update_date
        inventory_update_dates_wh2 = stock_update_ids_wh_2.inventory_update_date

        sws_update_dates_wh1 = stock_update_ids_wh_1.sws_update_date
        sws_update_dates_wh2 = stock_update_ids_wh_2.sws_update_date
        time.sleep(1)
        self.test_product_1.write({"eshop_sws_logic": "yes"})
        self.inventory_sws_date_assertions(
            old_sws=sws_update_dates_wh1,
            new_sws=stock_update_ids_wh_1.sws_update_date,
            should_match=False,
        )
        self.inventory_sws_date_assertions(
            old_sws=sws_update_dates_wh2,
            new_sws=stock_update_ids_wh_2.sws_update_date,
            should_match=False,
        )
        self.inventory_sws_date_assertions(
            old_inv=inventory_update_dates_wh1,
            new_inv=stock_update_ids_wh_1.inventory_update_date,
            should_match=True,
        )
        self.inventory_sws_date_assertions(
            old_inv=inventory_update_dates_wh2,
            new_inv=stock_update_ids_wh_2.inventory_update_date,
            should_match=True,
        )
        from_date = self.from_date - timedelta(days=1)
        to_date = self.to_date + timedelta(days=1)
        payload = self.get_payload_for_webhook(
            warehouses=self.wh_ref_keys,
            products=self.product_skus,
            from_date=from_date,
            to_date=to_date,
        )
        response = self.process_stock_update_webhook(payload)
        self.check_product_quant_and_inventory_date_webhook(
            response=response, record_count=3
        )
        self.env["stock.quant"].create(
            {
                "product_id": self.test_product_1.id,
                "location_id": self.wh1.lot_stock_id.id,
                "quantity": 10.0,
                "inventory_quantity": 10.0,
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": self.test_product_1.id,
                "quantity": 10.0,
                "location_id": self.wh2.lot_stock_id.id,
                "inventory_quantity": 10.0,
            }
        )

        self.env["stock.quant"].create(
            {
                "product_id": self.test_product_2.id,
                "location_id": self.wh1.lot_stock_id.id,
                "quantity": 10.0,
                "inventory_quantity": 10.0,
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": self.test_product_2.id,
                "quantity": 10.0,
                "location_id": self.wh2.lot_stock_id.id,
                "inventory_quantity": 10.0,
            }
        )
        # After quantity updation it will affect on inventory update date
        self.test_product_1.stock_quant_ids.flush_recordset()
        self.test_product_2.stock_quant_ids.flush_recordset()
        self.inventory_sws_date_assertions(
            old_inv=inventory_update_dates_wh1,
            new_inv=stock_update_ids_wh_1.inventory_update_date,
            should_match=False,
        )
        self.inventory_sws_date_assertions(
            old_inv=inventory_update_dates_wh2,
            new_inv=stock_update_ids_wh_2.inventory_update_date,
            should_match=False,
        )

        self.inventory_sws_date_assertions(
            old_sws=sws_update_dates_wh1,
            new_sws=stock_update_ids_wh_1.sws_update_date,
            should_match=False,
        )
        self.inventory_sws_date_assertions(
            old_sws=sws_update_dates_wh2,
            new_sws=stock_update_ids_wh_2.sws_update_date,
            should_match=False,
        )

        payload = self.get_payload_for_webhook(
            warehouses=self.wh_ref_keys,
            products=self.product_skus,
            from_date=from_date,
            to_date=to_date,
        )
        response = self.process_stock_update_webhook(payload)

        quantity_dict = {
            self.test_product_1.default_code: 10,
            self.test_product_2.default_code: 10,
        }
        self.check_product_quant_and_inventory_date_webhook(
            response=response, quantity_dict=quantity_dict, record_count=3
        )
        self.check_quant_and_inventory_date_from_delivery(
            {
                self.test_product_1.default_code: {
                    "demand_qty": 2,
                    "expected_qty": 8,
                },
                self.test_product_2.default_code: {
                    "demand_qty": 6,
                    "expected_qty": 4,
                },
            }
        )
