from os.path import dirname, join

from vcr import VCR

from odoo.tests.common import users

from .common import ScayleTestCases

recorder = VCR(
    cassette_library_dir=join(dirname(__file__), "fixtures/cassettes"),
    decode_compressed_response=True,
    filter_headers=["Authorization"],
    path_transformer=VCR.ensure_suffix(".yaml"),
    record_mode="once",
)


class TestCollectionPoint(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Configurations for scayle Sale Order to be of Collection Point. # T-02556"""
        super().setUpClass()
        cls.cp_dhl_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "CP DHL",
                "eshop_carrier_code": "DHL",
                "shipment_options": "collection_point_delivery",
                "required_attributes": "customerKey",
                "customer_key": "0987654345678",
                "address_key": "Charlottenstrasse 89",
                "product_id": cls.carrier_id.product_id.id,
            }
        )
        cls.hd_dhl_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "HD DHL",
                "eshop_carrier_code": "DHL",
                "product_id": cls.carrier_id.product_id.id,
            }
        )
        cls.dhl_address_dict = {
            "billing": {
                "street": "Silhofer Strasse114",
                "streetHouseNumber": "18344",
                "collectionPoint": {
                    "customerKey": "0987654345678",
                    "description": "Charlottenstrasse 89",
                    "key": "",
                    "type": "DHL",
                },
                "zipCode": "35573344",
                "city": "Wetzlar",
                "countryCode": "AT",
                "firstName": "Pledra111444",
                "lastName": "Team1444",
                "phoneNumber": "43-660-501-8669",
            },
            "shipping": {
                "street": "Silhofer Strasse22244442",
                "streetHouseNumber": "18222444",
                "collectionPoint": {
                    "customerKey": "0987654345678",
                    "description": "Charlottenstrasse 89",
                    "key": "",
                    "type": "DHL",
                },
                "zipCode": "35572244",
                "city": "Wetzlar2244",
                "countryCode": "AT",
                "firstName": "Pledra22244",
                "lastName": "Team22244",
                "phoneNumber": "43-660-501-8669",
            },
        }

    @users("sale_manager_and_inventory_manager")
    def test_01_home_delivery(self):
        """
        New Method: Added test case to check functionality for carrier as home delivery
        in scayle sale order. #T-02556
        """
        self.scayle_order_payload.update(
            {
                "carrier": {"key": "DHL"},
            }
        )
        self.external_id = self.scayle_order_payload.get("orderId")
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.external_id,
            data=self.scayle_order_payload,
        )

        self.sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id)]
        )
        so = self.sale_binding.odoo_id
        tag_names = so.tag_ids.mapped("name")
        self.assertNotIn("CP", tag_names, "CP tag should not be linked!")
        self.assertIn("ST", tag_names, "ST tag should be linked!")
        self.assertFalse(
            so.eshop_collection_point, "Scayle Collection Point should be True!"
        )
        so.action_confirm()
        self.assertEqual(
            so.picking_ids.carrier_id, self.hd_dhl_carrier, "Carrir should be same!"
        )

    @users("sale_manager_and_inventory_manager")
    def test_02_collection_point(self):
        """
        New Method: Added test case to check functionality for carrier as collection
        Point in scayle sale order. #T-02556
        """
        self.scayle_order_payload.update(
            {
                "carrier": {"key": "DHL"},
                "addresses": self.dhl_address_dict,
            }
        )
        self.external_id = self.scayle_order_payload.get("orderId")
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.external_id,
            data=self.scayle_order_payload,
        )

        self.sale_binding_1 = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id)]
        )
        so = self.sale_binding_1.odoo_id
        tag_names = so.tag_ids.mapped("name")
        self.assertIn("CP", tag_names, "CP tag should be linked!")
        self.assertIn("ST", tag_names, "ST tag should be linked!")
        self.assertTrue(
            so.eshop_collection_point, "Scayle Collection Point should be True!"
        )
        so.action_confirm()
        self.assertEqual(
            so.picking_ids.carrier_id, self.cp_dhl_carrier, "Carrir should be same!"
        )
