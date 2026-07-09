import copy

import odoo
from odoo.tests import common
from odoo.tests.common import users
from odoo.tools import mute_logger

from .common import ScayleTestCases


@common.tagged("post_install", "-at_install")
class ScayleOrderTestCases(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Configurations for importing sale order from Scayle. # T-02660"""
        super().setUpClass()
        cls.order_webhook_url = "api/scayle/v1/order-create/{}".format(
            cls.scayle_backend.test_odoo_scayle_token
        )
        cls.base_url = "http://{}:{}".format(
            common.HOST, odoo.tools.config["http_port"]
        )

    def create_duplicate_scayle_order_payload(self):
        """#T-02660 Create and return a duplicate Scayle order payload."""
        payload = copy.deepcopy(self.scayle_order_payload)
        return payload

    def test_order_creation_webhook(self, payload=False):
        """#T-02250 Called webhook for sale order"""
        scayle_response = self.opener.post(
            url=f"{self.base_url}/{self.order_webhook_url}",
            json=payload or self.scayle_order_payload,
        )
        response = scayle_response.json()
        return response

    @users("sale_manager")
    def test_cod_order_creation_webhook(self):
        """#T-02556 Called webhook for sale order."""
        self.base_url = "http://{}:{}".format(
            common.HOST, odoo.tools.config["http_port"]
        )
        response = self.opener.post(
            url=f"{self.base_url}/{self.order_webhook_url}",
            json=self.scayle_cz_order_payload,
        )
        self.assertEqual(response.status_code, 200, "Should be OK")
        response = response.json()
        self.assertEqual(
            response.get("result").get("referenceKey"),
            self.scayle_cz_order_payload.get("orderId", ""),
            "Order Reference Key should match!",
        )

    @users("sale_manager")
    def test_no_country_code_in_shipping_add_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        no country code in shipping address in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload["addresses"]["shipping"].update({"countryCode": ""})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = "Missing customer countryCode in shipping address."
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_items_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        no items in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload.update({"items": []})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = "Items is missing/empty in the payload."
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_duplicate_orderitem_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        duplicate orderitems in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload["items"][1].update({"orderItemId": "1968655"})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
            "odoo.http",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = (
            "The duplicate orderItemId found in payload. They are : 1968655"
        )
        error_message = response.get("error", {}).get("data", {}).get("message", "")
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_product_sku_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        no product sku in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload["items"][1].update({"merchantProductVariantReferenceKey": ""})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = (
            "The 'merchantProductVariantReferenceKey' is missing "
            "in items ids : 1968656."
        )
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_wrong_product_sku_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        wrong product sku in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload["items"][1].update({"merchantProductVariantReferenceKey": "123123123"})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = (
            "Product not found with default code"
            " (merchantProductVariantReferenceKey) 123123123 in odoo."
        )
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_carrier_key_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        no shipping carrier key in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload["carrier"].update({"key": ""})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = "Carrier key is missing in the payload."
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_data_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        empty scayle payload. # T-02660
        """
        self.scayle_order_payload = {}
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
            "odoo.http",
        ):
            response = self.test_order_creation_webhook()
        expected_error_message = (
            "The Combination of Access Token(52d1ce46-af59-468d-91a2-a06f0aa54e61), "
            "ShopKey(None), CountryCode(None), and ShopId(None) is Invalid!"
        )
        error_message = response.get("error", {}).get("data", {}).get("message", "")
        self.assertEqual(
            "".join(expected_error_message.split()),
            "".join(error_message.split()),
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_order_id_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        no order_id or external_id in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload.update({"orderId": ""})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = "orderId is missing from the payload."
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_order_reference_key_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        no orderReferenceKey in scayle payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload.update({"orderReferenceKey": ""})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = "'orderReferenceKey' is missing from the payload"
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_email_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        no email in customer in scayle order payload. # T-02660
        """
        payload = self.create_duplicate_scayle_order_payload()
        payload["customer"].update({"email": ""})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook(payload)
        expected_error_message = (
            "Customer email is missing from the payload for 'referenceKey' %s."
            % self.scayle_order_payload.get("customer").get("referenceKey")
        )
        status_code = response.get("result", {}).get("statusCode")
        error_message = response.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_order_creation_with_collection_point(self):
        """
        New Method: Added test cases to get successfully the response from webhook .
        # T-02660
        """
        # T-02857 check current user as sales manager.
        self.assertEqual(
            self.env.user,
            self.sale_manager,
            "Current User is not the Sales Manager",
        )
        self.cp_dhl_carrier = self.env["delivery.carrier"].create(
            {
                "name": "CP DHL",
                "eshop_carrier_code": "DHL",
                "shipment_options": "collection_point_delivery",
                "required_attributes": "customerKey",
                "customer_key": "0987654345678",
                "address_key": "Charlottenstrasse 89",
                "product_id": self.carrier_id.product_id.id,
            }
        )
        self.scayle_order_payload["addresses"]["shipping"].update(
            {
                "collectionPoint": {
                    "customerKey": "0987654345678",
                    "description": "Charlottenstrasse 89",
                    "key": "",
                    "type": "DHL",
                },
            }
        )
        self.scayle_order_payload["addresses"]["billing"].update(
            {
                "collectionPoint": {
                    "customerKey": "0987654345678",
                    "description": "Charlottenstrasse 89",
                    "key": "",
                    "type": "DHL",
                },
            }
        )
        self.scayle_order_payload["cost"].update(
            {
                "appliedFees": [
                    {
                        "category": "delivery",
                        "key": "at_post_at_standard",
                        "option": "deliveryCosts",
                        "tax": {"vat": {"amount": 8280, "rate": 0.23}},
                        "amount": {"withoutTax": 27720, "withTax": 36000},
                    }
                ],
            }
        )
        self.scayle_order_payload.update({"carrier": {"key": "DHL"}})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response = self.test_order_creation_webhook()
        status_code = response.get("result", {}).get("statusCode")
        self.assertEqual(
            status_code,
            201,
            "Status code should be 201.",
        )
        self.assertEqual(
            response.get("result").get("referenceKey"),
            self.scayle_order_payload.get("orderId", ""),
            "Importing Scayle Order from webhook failed, Please check!",
        )

    # Renamed the method for executing sequence to ensure it is executed last
    @users("sale_manager")
    def test_z_collection_point_and_applied_fees_validations(self):
        """
        New Method: Added test cases to get successfully the response from webhook .
        # T-02660
        """
        self.cp_dhl_carrier = self.env["delivery.carrier"].create(
            {
                "name": "CP DHL",
                "eshop_carrier_code": "DHL",
                "shipment_options": "collection_point_delivery",
                "required_attributes": "customerKey",
                "customer_key": "0987654345678",
                "address_key": "Charlottenstrasse 89",
                "product_id": self.carrier_id.product_id.id,
            }
        )
        self.scayle_order_payload["addresses"]["shipping"].update(
            {
                "collectionPoint": {
                    "customerKey": "0987654345678",
                    "description": "Charlottenstrasse 89",
                    "key": "",
                    "type": "DHL",
                },
            }
        )
        self.scayle_order_payload["addresses"]["billing"].update(
            {
                "collectionPoint": {
                    "customerKey": "0987654345678",
                    "description": "Charlottenstrasse 89",
                    "key": "",
                    "type": "DHL",
                },
            }
        )
        self.scayle_order_payload["cost"].update(
            {
                "appliedFees": [
                    {
                        "category": "delivery",
                        "key": "at_post_at_standard",
                        "option": "deliveryCosts",
                        "tax": {"vat": {"amount": 8280, "rate": 0.23}},
                        "amount": {"withoutTax": 27720, "withTax": 36000},
                    },
                    {
                        "category": "repair",
                        "key": "at_post_at_standard",
                        "option": "repairCost",
                        "tax": {"vat": {"amount": 8280, "rate": 0.23}},
                        "amount": {"withoutTax": 27720, "withTax": 36000},
                    },
                ],
            }
        )
        self.scayle_order_payload.update({"carrier": {"key": "DHL"}})
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response_1 = self.test_order_creation_webhook()
        expected_error_message_1 = (
            "Only 1 entry of option 'deliveryCosts' is supported in appliedFees."
        )
        status_code_1 = response_1.get("result", {}).get("statusCode")
        error_message_1 = response_1.get("result", {}).get("message")
        self.assertEqual(
            status_code_1,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message_1,
            expected_error_message_1,
            "Error message should match!, Please check",
        )
        self.scayle_order_payload["addresses"]["shipping"].update(
            {
                "collectionPoint": {
                    "customerKey": "",
                    "description": "Charlottenstrasse 89",
                    "key": "",
                    "type": "DHL",
                },
            }
        )
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response_2 = self.test_order_creation_webhook()
        expected_error_message_2 = (
            "'customerKey' key or value is missing in the payload in shipping address "
            "collectionPoint for type carrier DHL."
        )
        status_code_2 = response_2.get("result", {}).get("statusCode")
        error_message_2 = response_2.get("result", {}).get("message")
        self.assertEqual(
            status_code_2,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message_2,
            expected_error_message_2,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_no_duplicate_so_validation(self):
        """
        New Method: Added test cases to check for Validation errors raised with
        duplicate scayle order payload or already imported. # T-02660
        """
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.scayle_order_payload.get("orderId"),
            data=self.scayle_order_payload,
        )
        with mute_logger(
            "odoo.addons.connector_scayle.controllers.order_creation",
        ):
            response_2 = self.test_order_creation_webhook()
        expected_error_message = "The sale order is already imported."
        status_code = response_2.get("result", {}).get("statusCode")
        error_message = response_2.get("result", {}).get("message")
        self.assertEqual(
            status_code,
            400,
            "Status code should be 400 as we are raising Validation Errors.",
        )
        self.assertEqual(
            error_message,
            expected_error_message,
            "Error message should match!, Please check",
        )

    @users("sale_manager")
    def test_auto_confirm_sale_order(self):
        """
        New Method: Added test cases to check for auto confirm sale order. # T-02726
        """
        self.scayle_backend.write({"auto_confirm_order": True})
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.scayle_order_payload.get("orderId"),
            data=self.scayle_order_payload,
        )
        external_id = self.scayle_order_payload.get("orderId")
        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", external_id)]
        )
        sale_order_state = sale_binding.odoo_id.state
        self.assertEqual(
            sale_order_state,
            "sale",
            "Sale order should be in 'sale' state",
        )

    @users("sale_manager")
    def test_confirm_sale_order_for_unified_warehouse(self):
        """
        #T-02849 New/Test Method: To check order line route set is of unified
        warehouse.
        """
        self.scayle_backend.company_id.eshop_unified_warehouse_id = self.wh2
        self.scayle_backend.write({"auto_confirm_order": True})
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.scayle_order_payload.get("orderId"),
            data=self.scayle_order_payload,
        )
        external_id = self.scayle_order_payload.get("orderId")
        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", external_id)]
        )
        sale_order_state = sale_binding.odoo_id.state
        w2_route = self.wh2.delivery_route_id
        sale_order_line = sale_binding.odoo_id.order_line
        self.assertEqual(
            sale_order_state,
            "sale",
            "Sale order should be in 'sale' state",
        )
        self.assertEqual(
            w2_route,
            sale_order_line[0].route_id,
            "Route should be of warehouse2 for order line",
        )
        self.assertEqual(
            w2_route,
            sale_order_line[1].route_id,
            "Route should be of warehouse2 for order line",
        )

    @users("sale_manager_and_inventory_manager")
    def test_confirm_sale_order_for_initial_warehouse(self):
        """
        #T-02849 New/Test Method: To check order line route set is of initial
        warehouse.
        """
        self.scayle_backend.company_id.eshop_unified_warehouse_id = self.wh2
        self.env["stock.quant"].create(
            {
                "product_id": self.product_storable.id,
                "location_id": self.wh1.lot_stock_id.id,
                "quantity": 5.0,
            }
        )
        self.scayle_backend.write({"auto_confirm_order": True})
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.scayle_cz_order_payload_2.get("orderId"),
            data=self.scayle_cz_order_payload_2,
        )
        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id_2)]
        )
        sale_order_state = sale_binding.odoo_id.state
        w1_route = self.wh1.delivery_route_id
        sale_order_line = sale_binding.odoo_id.order_line
        self.assertEqual(
            sale_order_state,
            "sale",
            "Sale order should be in 'sale' state",
        )
        self.assertEqual(
            w1_route,
            sale_order_line[0].route_id,
            "Route should be of warehouse1 for order line",
        )

    @users("sale_manager")
    def test_cancel_selected_lines_flow(self):
        """
        #T-03065 Test: Import order and cancel scayle lines via button
        """
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.scayle_order_payload.get("orderId"),
            data=self.scayle_order_payload,
        )
        external_id = self.scayle_order_payload.get("orderId")
        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", external_id)]
        )
        sale_order = sale_binding.odoo_id
        scayle_lines = sale_order.mapped("scayle_line_ids")

        self.assertTrue(scayle_lines, "Scayle lines should exist after import")
        scayle_lines.action_cancel_selected_lines()
        for line in scayle_lines:
            self.assertTrue(
                line.cancel_in_odoo,
                "Line should be marked as cancelled in Odoo",
            )
