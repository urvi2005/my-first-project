from odoo.tests.common import users
from odoo.tools import mute_logger

from odoo.addons.component.core import WorkContext
from odoo.addons.component.tests.common import TransactionComponentRegistryCase
from odoo.addons.connector.exception import MappingError

from .common import ScayleTestCases


class TestScayleErrors(ScayleTestCases, TransactionComponentRegistryCase):
    @classmethod
    def setUpClass(cls):
        """#T-02256 Configurations for scayle importer components."""
        super().setUpClass()
        cls._setup_registry(cls)
        cls._load_module_components(cls, "connector_scayle")
        cls.sale_order_work = WorkContext(
            model_name="scayle.sale.order",
            collection=cls.scayle_backend,
            components_registry=cls.comp_registry,
        )
        cls.import_mapper_component = cls.sale_order_work.component(
            usage="import.mapper", model_name="scayle.sale.order"
        )

    @users("sale_manager")
    def test_mapping_error_for_fielmann_order_number(self):
        """
        New Method: Added test case to check for Mapping Error for
        fielmann_order_number # T-02660
        """
        self.scayle_order_payload.update({"orderReferenceKey": ""})
        with self.assertRaises(MappingError):
            self.import_mapper_component.fielmann_order_number(
                self.scayle_order_payload
            )

    @users("sale_manager")
    def test_mapping_error_for_scayle_currency_id(self):
        """
        New Method: Added test case to check for Mapping Error for
        scayle_currency_id # T-02660
        """
        self.scayle_order_payload["items"][0].update({"currencyCode": "APR"})
        with self.assertRaises(MappingError):
            self.import_mapper_component.eshop_currency_id(self.scayle_order_payload)
        self.scayle_order_payload["items"][1].update({"currencyCode": "APR"})
        self.scayle_order_payload["items"][2].update({"currencyCode": "APR"})
        with self.assertRaises(MappingError):
            self.import_mapper_component.eshop_currency_id(self.scayle_order_payload)

    @users("sale_manager")
    def test_mapping_of_scayle_price_with_tax(self):
        """
        New Method: Added test case to check for Mapping of scayle_price_with_tax.
        # T-02660
        """
        self.scayle_order_payload["cost"].update({"withTax": 0})
        expected_mapping_of_so_price_with_tax = {}
        mapping_of_so_price_with_tax = (
            self.import_mapper_component.eshop_price_with_tax(self.scayle_order_payload)
        )
        self.assertEqual(
            expected_mapping_of_so_price_with_tax,
            mapping_of_so_price_with_tax,
            "Mapping of Price With tax should be same.",
        )

    @users("sale_manager")
    def test_02_mapping_of_scayle_price_without_tax(self):
        """
        New Method: Added test case to check for Mapping of scayle_price_without_tax.
        # T-02660
        """
        self.scayle_order_payload["cost"].update({"withoutTax": 0})
        expected_mapping_of_so_price_without_tax = {}
        mapping_of_so_price_without_tax = (
            self.import_mapper_component.eshop_price_without_tax(
                self.scayle_order_payload
            )
        )
        self.assertEqual(
            expected_mapping_of_so_price_without_tax,
            mapping_of_so_price_without_tax,
            "Mapping of Price Without tax should be same.",
        )

    @users("sale_manager")
    def test_01_mapping_of_scayle_tax_amount(self):
        """
        New Method: Added test case to check for Mapping of scayle_tax_amount
        # T-02660
        """
        self.scayle_order_payload["cost"]["tax"]["vat"].update({"amount": 0})
        expected_mapping_of_tax_amount = {}
        mapping_of_so_tax_amount = self.import_mapper_component.eshop_tax_amount(
            self.scayle_order_payload
        )
        self.assertEqual(
            expected_mapping_of_tax_amount,
            mapping_of_so_tax_amount,
            "Mapping of Tax amount should be same.",
        )

    @users("sale_manager")
    def test_mapping_of_scayle_shipping_tax_amount(self):
        """
        New Method: Added test case to check for Mapping of
        scayle_shipping_tax_amount # T-02660
        """
        applied_fees = {
            "appliedFees": [
                {
                    "category": "delivery",
                    "key": "at_post_at_standard",
                    "option": "deliveryCosts",
                    "tax": {"vat": {"amount": 0, "rate": 0.23}},
                    "amount": {"withoutTax": 27720, "withTax": 36000},
                }
            ],
        }
        self.scayle_order_payload.update({"cost": applied_fees})
        expected_mapping_of_shipping_tax_amount = {}
        mapping_of_shipping_tax_amount = (
            self.import_mapper_component.eshop_shipping_tax_amount(
                self.scayle_order_payload
            )
        )
        self.assertEqual(
            expected_mapping_of_shipping_tax_amount,
            mapping_of_shipping_tax_amount,
            "Mapping of Tax amount of shipping line should be same.",
        )

    @users("sale_manager")
    def test_mapping_of_scayle_shipping_with_tax_price(self):
        """
        New Method: Added test case to check for Mapping of
        scayle_shipping_with_tax_price # T-02660
        """
        applied_fees = {
            "appliedFees": [
                {
                    "category": "delivery",
                    "key": "at_post_at_standard",
                    "option": "deliveryCosts",
                    "tax": {"vat": {"amount": 8280, "rate": 0.23}},
                    "amount": {"withoutTax": 27720, "withTax": 0},
                }
            ],
        }
        self.scayle_order_payload.update({"cost": applied_fees})
        expected_mapping_of_shipping_price_with_tax = {}
        mapping_of_shipping_price_with_tax = (
            self.import_mapper_component.eshop_shipping_with_tax_price(
                self.scayle_order_payload
            )
        )
        self.assertEqual(
            expected_mapping_of_shipping_price_with_tax,
            mapping_of_shipping_price_with_tax,
            "Mapping of Price With Tax of shipping line should be same.",
        )

    @users("sale_manager")
    def test_mapping_of_scayle_shipping_without_tax_price(self):
        """
        New Method: Added test case to check for Mapping of
        scayle_shipping_without_tax_price # T-02660
        """
        applied_fees = {
            "appliedFees": [
                {
                    "category": "delivery",
                    "key": "at_post_at_standard",
                    "option": "deliveryCosts",
                    "tax": {"vat": {"amount": 8280, "rate": 0.23}},
                    "amount": {"withoutTax": 0, "withTax": 36000},
                }
            ],
        }
        self.scayle_order_payload.update({"cost": applied_fees})
        expected_mapping_of_shipping_price_without_tax = {}
        mapping_of_shipping_price_without_tax = (
            self.import_mapper_component.eshop_shipping_without_tax_price(
                self.scayle_order_payload
            )
        )
        self.assertEqual(
            expected_mapping_of_shipping_price_without_tax,
            mapping_of_shipping_price_without_tax,
            "Mapping of Price Without Tax of shipping line should be same.",
        )

    @users("sale_manager")
    def test_mapping_of_scayle_shipping_tax_rate(self):
        """
        New Method: Added test case to check for Mapping of scayle_shipping_tax_rate
        # T-02660
        """
        applied_fees = {
            "appliedFees": [
                {
                    "category": "delivery",
                    "key": "at_post_at_standard",
                    "option": "deliveryCosts",
                    "tax": {"vat": {"amount": 8280, "rate": 0}},
                    "amount": {"withoutTax": 27720, "withTax": 36000},
                }
            ],
        }
        self.scayle_order_payload.update({"cost": applied_fees})
        expected_mapping_of_shipping_price_without_tax = {}
        mapping_of_shipping_price_without_tax = (
            self.import_mapper_component.eshop_shipping_tax_rate(
                self.scayle_order_payload
            )
        )
        self.assertEqual(
            expected_mapping_of_shipping_price_without_tax,
            mapping_of_shipping_price_without_tax,
            "Mapping of Price Without Tax of shipping line should be same.",
        )

    @users("sale_manager")
    def test_mapping_of_date_order(self):
        """
        New Method: Added test case to check for Mapping of date_order
        # T-02660
        """
        self.scayle_order_payload.update({"confirmedAt": "12/24/2018, 04:59:31"})
        expected_mapping_of_date_order = {
            "date_order": "2018-12-24 04:59:31",
            "scayle_date_order": "2018-12-24 04:59:31",
        }
        mapping_of_date_order = self.import_mapper_component.date_order(
            self.scayle_order_payload
        )
        self.assertEqual(
            expected_mapping_of_date_order,
            mapping_of_date_order,
            "Mapping of Date Order should be same.",
        )

    @users("sale_manager")
    def test_mapping_of_scayle_order_status(self):
        """
        New Method: Added test case to check for Mapping of scayle_order_status
        # T-02660
        """
        self.scayle_order_payload = {}
        expected_mapping_of_scayle_order_status = {}
        mapping_of_scayle_order_status = (
            self.import_mapper_component.scayle_order_status(self.scayle_order_payload)
        )
        self.assertEqual(
            expected_mapping_of_scayle_order_status,
            mapping_of_scayle_order_status,
            "Mapping of Order Status should be same.",
        )

    @users("sale_manager")
    def test_mapping_error_for_carrier_id(self):
        """
        New Method: Added test case to check for Mapping Error for delivery carrier
        # T-02660
        """
        self.scayle_order_payload["carrier"].update({"key": "APR"})
        self.external_id = self.scayle_order_payload.get("orderId")
        with self.assertRaises(MappingError):
            self.binding_model.import_record(
                backend=self.scayle_backend,
                external_id=self.external_id,
                data=self.scayle_order_payload,
            )

    @users("sale_manager")
    def test_no_company_at_backend(self):
        """
        New Method: Added test case to check for mapping error for no company
        found in backend. # T-02660
        """
        self.scayle_backend.company_id = False
        with self.assertRaises(MappingError):
            self.import_mapper_component.get_company()

    @users("sale_manager")
    def test_mapping_error_for_revenue_store(self):
        """
        New Method: Added test case to check for Mapping error for revenue_store
        # T-02660
        """
        self.scayle_order_payload.update({"branchNumber": ""})
        self.scayle_order_payload["customData"].update({"branchNumber": ""})
        with self.assertRaises(MappingError):
            self.import_mapper_component.partner_revenue(self.scayle_order_payload)

    @users("sale_manager")
    def test_scayle_line_tax(self):
        """New Method: Added test case to check for shipping line tax. # T-02660"""
        tax = self.env["scayle.sale.order.line"].get_scayle_line_tax(
            tax_percent=23, backend=self.scayle_backend
        )
        self.assertEqual(len(tax), 1, "One tax should be found.")
        with mute_logger("odoo.addons.connector_scayle.models.sale_order.common"):
            tax_2 = self.env["scayle.sale.order.line"].get_scayle_line_tax(
                tax_percent=25, backend=self.scayle_backend
            )
        self.assertEqual(len(tax_2), 0, "No tax should be found.")
