import json
import time
from datetime import datetime, timedelta
from os.path import dirname, join

from vcr import VCR

import odoo
from odoo import SUPERUSER_ID, fields
from odoo.tests import common

from odoo.addons.component.tests.common import TransactionComponentCase
from odoo.addons.connector_base_ecommerce.tests.test_warehouse_mrp import (
    MRPWarehouseCases,
)

from .payloads.frame_2_regular_1_payload import frame_2_regular_1_data

recorder = VCR(
    cassette_library_dir=join(dirname(__file__), "fixtures/cassettes"),
    decode_compressed_response=True,
    filter_headers=["Authorization"],
    path_transformer=VCR.ensure_suffix(".yaml"),
    record_mode="once",
)


class ScayleTestCases(common.HttpCase, TransactionComponentCase):
    @classmethod
    def setUpClass(cls):
        """#T-02250 configurations for the scayle backend"""
        super().setUpClass()
        cls.product_category = cls.env.ref("product.product_category_all")
        cls.scayle_url = "https://localhost:8069/api/public"
        cls.country_id = cls.env["res.country"].search([("code", "=", "AT")], limit=1)
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.company_id = cls.env.ref("base.main_company")
        eur_currency = (
            cls.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", "EUR")])
        )
        eur_currency.active = True
        cls.eur_pricelist = cls.env["product.pricelist"].create(
            {"name": "Default EUR Pricelist", "currency_id": eur_currency.id}
        )
        cls.carrier_id = cls.env.ref("connector_scayle.scayle_shipping_method")
        cls.backend_model = cls.env["scayle.backend"]
        cls.binding_model = cls.env["scayle.sale.order"]
        cls.scayle_shop_partner = cls.env["res.partner"].create(
            {
                "name": "AT",
                "is_intercompany": True,
            }
        )
        cls.branch_code = "0722"
        cls.shop_entity = cls.env.ref("connector_base_ecommerce.shop_entity_fielmann")
        cls.scayle_shop_partner.write(
            {
                "branch_code": cls.branch_code or "BR0001",
                "is_intercompany": True,
                "shop_entity_id": cls.shop_entity.id,
            }
        )
        sales_team = cls.env["crm.team"].create(
            {"name": cls.scayle_shop_partner.name, "company_id": cls.company_id.id}
        )
        cls.at_scayle_shop = cls.env["scayle.shop"].create(
            {
                "name": cls.scayle_shop_partner.name,
                "partner_id": cls.scayle_shop_partner.id,
                "sales_team_id": sales_team.id,
            }
        )
        cls.backendGroup = cls.env["backend.group"]
        cls.test_backend_group_access_token1 = "52d1ce46-af59-468d-91a2-a06f0aa54e61"
        cls.test_backend_group_access_token2 = "52d1ce46-af59-468d-91a2-a06f0aa54e62"
        cls.scayle_group = cls.backendGroup.create(
            {
                "name": "Scayle Group",
                "backend_group_access_token": "52d1ce46-af59-468d-91a2-a06f0aa54e61",
                "test_backend_group_access_token": cls.test_backend_group_access_token1,
            }
        )
        cls.magento_group = cls.backendGroup.create(
            {
                "name": "Magento Group",
                "backend_group_access_token": "91d2re46-tf59-4h8d-95a6-a03f0ej88360",
                "test_backend_group_access_token": cls.test_backend_group_access_token2,
            }
        )
        cls.product_category.min_threshold_qty = 5
        cls.scayleStockRatio = cls.env["eshop.stock.ratio"]
        cls.scayle_ratio1 = cls.scayleStockRatio.create(
            {
                "backend_group_id": cls.magento_group.id,
                "product_categ_id": cls.product_category.id,
            }
        )
        cls.scayle_ratio2 = cls.scayleStockRatio.create(
            {
                "backend_group_id": cls.scayle_group.id,
                "product_categ_id": cls.product_category.id,
                "percentage": 100,
            }
        )
        cls.scayle_backend = cls.backend_model.create(
            {
                "name": "Test Scayle",
                "version": "v1",
                "test_location": cls.scayle_url,
                "shop_key": "fa",
                "country_id": cls.country_id.id,
                "test_token": "test",
                "warehouse_ids": [(4, cls.warehouse.id)],
                "default_pricelist_id": cls.eur_pricelist.id,
                "test_mode": True,
                "sale_prefix": "SCAYLE-AT",
                "test_odoo_scayle_token": "52d1ce46-af59-468d-91a2-a06f0aa54e61",
                "company_id": cls.company_id.id,
                "code": "AT",
                "shop_id": "10001",
                "backend_group_id": cls.scayle_group.id,
                "scayle_shop_id": cls.at_scayle_shop.id,
                "auto_confirm_order": False,
            }
        )
        cls.wh1 = cls.env["stock.warehouse"].create(
            {
                "name": "Warehouse1",
                "code": "WH1",
                "warehouse_reference_key": "WH1",
                "company_id": cls.company_id.id,
            }
        )
        cls.wh2 = cls.env["stock.warehouse"].create(
            {
                "name": "Warehouse2",
                "code": "WH2",
                "warehouse_reference_key": "WH2",
                "company_id": cls.company_id.id,
            }
        )
        # Configurations to create multiple DO's for mixed basket order.
        # START
        cls.wh1.route_ids[1].sale_selectable = True
        cls.wh1.route_ids[1].rule_ids[0].warehouse_id = False
        wh2_route = cls.wh2.route_ids[1]
        wh2_route.sale_selectable = True
        wh2_route.rule_ids[0].warehouse_id = False
        # END
        vendor = cls.env.ref("base.res_partner_address_13")
        seller_ids = [
            (
                0,
                0,
                {
                    "partner_id": vendor.id,
                    "company_id": cls.company_id.id,
                    "price": 12,
                    "product_code": "123456",
                },
            )
        ]
        cls.test_product_1 = cls.env["product.product"].create(
            {
                "name": "TEST1",
                "standard_price": 100.0,
                "default_code": "test_1",
                "type": "product",
                "eshop_sws_logic": "from_category",
                "barcode": "test-barcode-1",
            }
        )
        cls.test_product_2 = cls.env["product.product"].create(
            {
                "name": "TEST2",
                "standard_price": 100.0,
                "default_code": "test_2",
                "type": "product",
                "eshop_sws_logic": "from_category",
                "barcode": "test-barcode-2",
            }
        )
        cls.test_product_1.write(
            {
                "seller_ids": seller_ids,
            }
        )
        cls.test_product_2.write(
            {
                "seller_ids": seller_ids,
            }
        )
        cls.from_date, cls.to_date = fields.Datetime.now(), fields.Datetime.now()
        cls.wh_ref_keys = [
            cls.wh1.warehouse_reference_key,
            cls.wh2.warehouse_reference_key,
        ]
        cls.tax_23 = cls.env["account.tax"].create(
            {
                "name": "Test 23",
                "amount": 23.00,
                "type_tax_use": "sale",
                "company_id": cls.scayle_backend.company_id.id,
            }
        )
        cls.scayle_order_payload = {
            "addresses": {
                "billing": {
                    "additional": "Lower Austria",
                    "city": "Schlag",
                    "collectionPoint": None,
                    "countryCode": "AT",
                    "firstName": "Doris",
                    "gender": "f",
                    "houseNumber": "96",
                    "lastName": "Oliver",
                    "phoneNumber": "06819526526",
                    "street": "Aspernstrasse",
                    "streetHouseNumber": "96 Aspernstrasse",
                    "zipCode": "2813",
                },
                "shipping": {
                    "additional": "Lower Austria",
                    "city": "Lehen",
                    "collectionPoint": None,
                    "countryCode": "AT",
                    "firstName": "Doris",
                    "gender": "f",
                    "houseNumber": "9",
                    "lastName": "Oliver",
                    "phoneNumber": "06819526526",
                    "state": None,
                    "street": "Untere Neugasse",
                    "streetHouseNumber": "43 Untere Neugasse",
                    "zipCode": "3281",
                },
            },
            "branchNumber": "0722",
            "carrier": {"key": "POST_AT"},
            "companyId": 1000,
            "cost": {
                "costCapture": 61690,
                "tax": {"vat": {"amount": 11535}},
                "withTax": 61690,
                "withTaxWithMembershipDiscountWithoutServiceCosts": 61690,
                "withoutTax": 50155,
                "withoutTaxWithMembershipDiscount": 50155,
            },
            "countryCode": "AT",
            "customData": {"branchNumber": "0722"},
            "customer": {
                "customData": [],
                "email": "dorisoliver2345@example.com",
                "publicKey": "763",
                "referenceKey": "763",
                "taxNumber": None,
                "vendorReferenceKey": None,
            },
            "customerPublicKey": None,
            "fulfillingMerchantKey": "fim",
            "id": 15174,
            "items": [
                {
                    "currencyCode": "EUR",
                    "customData": {"aybaOttoReservationDetails": []},
                    "id": 28306,
                    "localizedName": "Fielmann BD 039 MOD SUN CL",
                    "merchantKey": "default",
                    "merchantProductVariantId": 5059,
                    "merchantProductVariantReferenceKey": "1022643",
                    "merchantReservationKey": None,
                    "name": "Fielmann BD 039 MOD SUN CL",
                    "orderItemId": "1968655",
                    "packagingGroupId": None,
                    "price": 9900,
                    "priceWithoutTax": 8049,
                    "productVariantId": 5059,
                    "quantity": 1,
                    "shippingWarehouseReferenceKey": "WH1",
                    "tax": 23,
                    "taxAmount": 1851,
                    "vendorReferenceKey": None,
                    "vendorSize": None,
                    "warehouseReferenceKey": "WH1",
                },
                {
                    "currencyCode": "EUR",
                    "customData": {"aybaOttoReservationDetails": []},
                    "id": 28307,
                    "localizedName": "RAY-BAN RB 3025 AVIATOR",
                    "merchantKey": "default",
                    "merchantProductVariantId": 7916,
                    "merchantProductVariantReferenceKey": "738854",
                    "merchantReservationKey": None,
                    "name": "Ray-Ban RB 3025 AVIATOR",
                    "orderItemId": "1968656",
                    "packagingGroupId": None,
                    "price": 41890,
                    "priceWithoutTax": 34057,
                    "productVariantId": 7916,
                    "quantity": 1,
                    "shippingWarehouseReferenceKey": "WH1",
                    "tax": 23,
                    "taxAmount": 7833,
                    "vendorReferenceKey": None,
                    "vendorSize": None,
                    "warehouseReferenceKey": "WH1",
                },
                {
                    "currencyCode": "EUR",
                    "customData": {"aybaOttoReservationDetails": []},
                    "id": 28308,
                    "localizedName": "Fielmann BD 039 MOD SUN CL",
                    "merchantKey": "default",
                    "merchantProductVariantId": 5059,
                    "merchantProductVariantReferenceKey": "1022643",
                    "merchantReservationKey": None,
                    "name": "Fielmann BD 039 MOD SUN CL",
                    "orderItemId": "1968657",
                    "packagingGroupId": None,
                    "price": 9900,
                    "priceWithoutTax": 8049,
                    "productVariantId": 5059,
                    "quantity": 1,
                    "shippingWarehouseReferenceKey": "WH1",
                    "tax": 23,
                    "taxAmount": 1851,
                    "vendorReferenceKey": None,
                    "vendorSize": None,
                    "warehouseReferenceKey": "WH1",
                },
            ],
            "languageCode": "de_DE",
            "orderId": 99110901,
            "orderReferenceKey": "fapl-10006-99110901",
            "paymentMethod": "paypal_instant",
            "shopId": 10001,
            "shopKey": "fa",
            "vendorReferenceKey": None,
        }
        # Added if need to add shipping line explicilty. # T-02556
        cls.shipping_line_data = {
            "costCapture": 97690,
            "tax": {"vat": {"amount": 19815}},
            "withTax": 97690,
            "withTaxWithMembershipDiscountWithoutServiceCosts": 97690,
            "withoutTax": 77875,
            "withoutTaxWithMembershipDiscount": 77875,
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

        # Test COD cases
        cls.cz_country = cls.env["res.country"].search([("code", "=", "CZ")])
        cls.cz_currency = cls.env.ref("base.CZK")
        cls.cz_currency.active = True
        cls.czk_default_pricelist = cls.env["product.pricelist"].create(
            {"name": "Default CZK Pricelist", "currency_id": cls.cz_currency.id}
        )
        delivery_carrier_categ = cls.env.ref("delivery.product_category_deliveries")
        deliver_product = cls.env["product.product"].create(
            {
                "name": "Demo Shipping Method CZ",
                "type": "service",
                "categ_id": delivery_carrier_categ.id,
            }
        )
        cls.cod_delivery_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "CZ Carrier COD",
                "product_id": deliver_product.id,
                "eshop_carrier_code": "POST_CZ",
                "shipment_options": "home_cod",
            }
        )
        cls.hd_delivery_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "CZ Carrier HD",
                "product_id": deliver_product.id,
                "eshop_carrier_code": "POST_CZ",
                "shipment_options": "home_delivery",
            }
        )
        cls.cz_scayle_shop_partner = cls.env["res.partner"].create(
            {
                "name": "CZ",
                "is_intercompany": True,
            }
        )
        cz_sales_team = cls.env["crm.team"].create(
            {"name": cls.cz_scayle_shop_partner.name, "company_id": cls.company_id.id}
        )
        cls.cz_scayle_shop = cls.env["scayle.shop"].create(
            {
                "name": cls.cz_scayle_shop_partner.name,
                "partner_id": cls.cz_scayle_shop_partner.id,
                "sales_team_id": cz_sales_team.id,
            }
        )
        cls.branch_code = "0189"
        cls.shop_entity = cls.env.ref("connector_base_ecommerce.shop_entity_fielmann")
        cls.cz_scayle_shop_partner.write(
            {
                "branch_code": cls.branch_code or "BR0001",
                "is_intercompany": True,
                "shop_entity_id": cls.shop_entity.id,
            }
        )
        cls.cz_scayle_backend = cls.backend_model.create(
            {
                "name": "Test CZ Scayle",
                "version": "v1",
                "test_location": cls.scayle_url,
                "shop_key": "fa",
                "country_id": cls.cz_country.id,
                "test_token": "test",
                "warehouse_ids": [(6, 0, [cls.warehouse.id])],
                "default_pricelist_id": cls.czk_default_pricelist.id,
                "test_mode": True,
                "sale_prefix": "SCAYLE-CZ",
                "test_odoo_scayle_token": "52d1ce46-af59-468d-91a2-a06f0aa54e61",
                "company_id": cls.company_id.id,
                "code": "CZ",
                "shop_id": "10005",
                "scayle_shop_id": cls.cz_scayle_shop.id,
                "backend_group_id": cls.scayle_group.id,
                "cod_payment_method": "cz_cod",
                "auto_confirm_order": False,
            }
        )
        cls.scayle_cz_order_payload = {
            "orderId": 121111,
            "companyId": 1000,
            "shopId": 10005,
            "fulfillingMerchantKey": "fim",
            "customerPublicKey": None,
            "vendorReferenceKey": None,
            "cost": {
                "costCapture": 97690,
                "tax": {"vat": {"amount": 19815}},
                "withTax": 97690,
                "withTaxWithMembershipDiscountWithoutServiceCosts": 97690,
                "withoutTax": 77875,
                "withoutTaxWithMembershipDiscount": 77875,
                "appliedFees": [
                    {
                        "category": "delivery",
                        "key": "at_post_at_standard",
                        "option": "deliveryCosts",
                        "tax": {"vat": {"amount": 8280, "rate": 0.23}},
                        "amount": {"withoutTax": 27720, "withTax": 36000},
                    }
                ],
            },
            "items": [
                {
                    "currencyCode": "CZK",
                    "customData": {"aybaOttoReservationDetails": []},
                    "id": 28306,
                    "localizedName": "Fielmann BD 039 MOD SUN CL",
                    "merchantKey": "default",
                    "merchantProductVariantId": 5059,
                    "merchantProductVariantReferenceKey": "1022643",
                    "merchantReservationKey": None,
                    "name": "Fielmann BD 039 MOD SUN CL",
                    "orderItemId": "1968655",
                    "packagingGroupId": None,
                    "price": 9900,
                    "priceWithoutTax": 8049,
                    "productVariantId": 5059,
                    "quantity": 1,
                    "shippingWarehouseReferenceKey": "WH1",
                    "tax": 23,
                    "taxAmount": 1851,
                    "vendorReferenceKey": None,
                    "vendorSize": None,
                    "warehouseReferenceKey": "WH1",
                },
                {
                    "currencyCode": "CZK",
                    "customData": {"aybaOttoReservationDetails": []},
                    "id": 28307,
                    "localizedName": "RAY-BAN RB 3025 AVIATOR",
                    "merchantKey": "default",
                    "merchantProductVariantId": 7916,
                    "merchantProductVariantReferenceKey": "738854",
                    "merchantReservationKey": None,
                    "name": "Ray-Ban RB 3025 AVIATOR",
                    "orderItemId": "1968656",
                    "packagingGroupId": None,
                    "price": 41890,
                    "priceWithoutTax": 34057,
                    "productVariantId": 7916,
                    "quantity": 1,
                    "shippingWarehouseReferenceKey": "WH1",
                    "tax": 23,
                    "taxAmount": 7833,
                    "vendorReferenceKey": None,
                    "vendorSize": None,
                    "warehouseReferenceKey": "WH1",
                },
                {
                    "currencyCode": "CZK",
                    "customData": {"aybaOttoReservationDetails": []},
                    "id": 28308,
                    "localizedName": "Fielmann BD 039 MOD SUN CL",
                    "merchantKey": "default",
                    "merchantProductVariantId": 5059,
                    "merchantProductVariantReferenceKey": "1022643",
                    "merchantReservationKey": None,
                    "name": "Fielmann BD 039 MOD SUN CL",
                    "orderItemId": "1968657",
                    "packagingGroupId": None,
                    "price": 9900,
                    "priceWithoutTax": 8049,
                    "productVariantId": 5059,
                    "quantity": 1,
                    "shippingWarehouseReferenceKey": "WH1",
                    "tax": 23,
                    "taxAmount": 1851,
                    "vendorReferenceKey": None,
                    "vendorSize": None,
                    "warehouseReferenceKey": "WH1",
                },
            ],
            "orderReferenceKey": "faat-1211",
            "shopKey": "fa",
            "countryCode": "CZ",
            "customer": {
                "referenceKey": "20011",
                "publicKey": None,
                "vendorReferenceKey": None,
                "taxNumber": None,
                "email": "demo@123.com",
                "customData": [],
            },
            "addresses": {
                "billing": {
                    "additional": "Lower Austria",
                    "city": "Prague",
                    "collectionPoint": None,
                    "countryCode": "CZ",
                    "firstName": "Petr",
                    "gender": "m",
                    "houseNumber": "20",
                    "lastName": "Novak",
                    "phoneNumber": "+420123456789",
                    "street": "Václavské náměstí",
                    "streetHouseNumber": "20 Václavské náměstí",
                    "zipCode": "110 00",
                },
                "shipping": {
                    "additional": "Lower Austria",
                    "city": "Brno",
                    "collectionPoint": None,
                    "countryCode": "CZ",
                    "firstName": "Eva",
                    "gender": "f",
                    "houseNumber": "15",
                    "lastName": "Nováková",
                    "phoneNumber": "+420987654321",
                    "state": "Jihomoravský kraj",
                    "street": "Masarykova",
                    "streetHouseNumber": "15 Masarykova",
                    "zipCode": "602 00",
                },
            },
            "customData": {},
            "paymentMethod": "cz_cod",
            "languageCode": "cs_CZ",
            "branchNumber": "0189",
            "carrier": {"key": "POST_CZ"},
        }
        cls.external_id = cls.scayle_cz_order_payload.get("orderId")
        # T-02849 Added new product and scayle_cz_order
        cls.product_storable = cls.env["product.product"].create(
            {
                "name": "Test Product Storable",
                "type": "product",
                "default_code": "1234",
                "categ_id": cls.product_category.id,
            }
        )
        cls.scayle_cz_order_payload_2 = {
            "orderId": 122111,
            "companyId": 1000,
            "shopId": 10005,
            "fulfillingMerchantKey": "fim",
            "customerPublicKey": None,
            "vendorReferenceKey": None,
            "cost": {
                "costCapture": 97690,
                "tax": {"vat": {"amount": 19815}},
                "withTax": 97690,
                "withTaxWithMembershipDiscountWithoutServiceCosts": 97690,
                "withoutTax": 77875,
                "withoutTaxWithMembershipDiscount": 77875,
                "appliedFees": [
                    {
                        "category": "delivery",
                        "key": "at_post_at_standard",
                        "option": "deliveryCosts",
                        "tax": {"vat": {"amount": 8280, "rate": 0.23}},
                        "amount": {"withoutTax": 27720, "withTax": 36000},
                    }
                ],
            },
            "items": [
                {
                    "currencyCode": "CZK",
                    "customData": {"aybaOttoReservationDetails": []},
                    "id": 28306,
                    "localizedName": "Fielmann BD 039 MOD SUN CL",
                    "merchantKey": "default",
                    "merchantProductVariantId": 5059,
                    "merchantProductVariantReferenceKey": "1234",
                    "merchantReservationKey": None,
                    "name": "Fielmann BD 039 MOD SUN CL",
                    "orderItemId": "1968655",
                    "packagingGroupId": None,
                    "price": 9900,
                    "priceWithoutTax": 8049,
                    "productVariantId": 5059,
                    "quantity": 1,
                    "shippingWarehouseReferenceKey": "WH1",
                    "tax": 23,
                    "taxAmount": 1851,
                    "vendorReferenceKey": None,
                    "vendorSize": None,
                    "warehouseReferenceKey": "WH1",
                },
            ],
            "orderReferenceKey": "faat-1211",
            "shopKey": "fa",
            "countryCode": "CZ",
            "customer": {
                "referenceKey": "20011",
                "publicKey": None,
                "vendorReferenceKey": None,
                "taxNumber": None,
                "email": "demo@123.com",
                "customData": [],
            },
            "addresses": {
                "billing": {
                    "additional": "Lower Austria",
                    "city": "Prague",
                    "collectionPoint": None,
                    "countryCode": "CZ",
                    "firstName": "Petr",
                    "gender": "m",
                    "houseNumber": "20",
                    "lastName": "Novak",
                    "phoneNumber": "+420123456789",
                    "street": "Václavské náměstí",
                    "streetHouseNumber": "20 Václavské náměstí",
                    "zipCode": "110 00",
                },
                "shipping": {
                    "additional": "Lower Austria",
                    "city": "Brno",
                    "collectionPoint": None,
                    "countryCode": "CZ",
                    "firstName": "Eva",
                    "gender": "f",
                    "houseNumber": "15",
                    "lastName": "Nováková",
                    "phoneNumber": "+420987654321",
                    "state": "Jihomoravský kraj",
                    "street": "Masarykova",
                    "streetHouseNumber": "15 Masarykova",
                    "zipCode": "602 00",
                },
            },
            "customData": {},
            "paymentMethod": "cz_cod",
            "languageCode": "cs_CZ",
            "branchNumber": "0189",
            "carrier": {"key": "POST_CZ"},
        }
        cls.external_id_2 = cls.scayle_cz_order_payload_2.get("orderId")
        cls.product_skus = [
            cls.test_product_1.default_code,
            cls.test_product_2.default_code,
            cls.product_storable.default_code,
        ]
        # T-02857 Update sale and stock user
        cls.sale_manager = cls.env.ref("fielmann_base.user_sale_manager")
        # T-02857 Added allowed partners for intercompany.
        cls.sale_manager.allowed_intercompany_partner_ids = [
            (6, 0, [cls.scayle_shop_partner.id, cls.cz_scayle_shop_partner.id])
        ]
        cls.inventory_manager = cls.env.ref("fielmann_base.user_inventory_manager")
        # T-02857 Added allowed partners for intercompany.
        cls.inventory_manager.allowed_intercompany_partner_ids = [
            (6, 0, [cls.scayle_shop_partner.id, cls.cz_scayle_shop_partner.id])
        ]
        cls.sale_and_inventory_manager = cls.env.ref(
            "fielmann_base.user_sale_manager_and_inventory_manager"
        )
        # T-02857 Added allowed partners for intercompany.
        cls.sale_and_inventory_manager.allowed_intercompany_partner_ids = [
            (6, 0, [cls.scayle_shop_partner.id, cls.cz_scayle_shop_partner.id])
        ]
        cls.connector_sale_inventory = cls.env.ref(
            "fielmann_base.user_connector_sale_inventory_manager"
        )
        # T-02857 Added allowed partners for intercompany.
        cls.connector_sale_inventory.allowed_intercompany_partner_ids = [
            (6, 0, [cls.scayle_shop_partner.id, cls.cz_scayle_shop_partner.id])
        ]
        # T-02857 updating the user admin rights.
        cls.admin = cls.env.ref("base.user_admin")
        group_xml_ids = [
            "stock.group_stock_manager",
            "sales_team.group_sale_manager",
            "base.group_partner_manager",
            "connector.group_connector_manager",
            "purchase.group_purchase_manager",
            "connector_base_ecommerce.group_partner_revenue_store_editable",
            "queue_job.group_queue_job_manager",
        ]
        cls.admin.groups_id = [(6, 0, [cls.env.ref(g).id for g in group_xml_ids])]
        # T-02857 Added allowed partners for intercompany.
        cls.admin.allowed_intercompany_partner_ids = [
            (6, 0, [cls.scayle_shop_partner.id, cls.cz_scayle_shop_partner.id])
        ]

    def process_stock_update_webhook(self, payload):
        """#T-02331 Generic method to returns the webhook response"""
        order_webhook_url = "/api/scayle/v1/get-stock-update/{}".format(
            self.scayle_backend.test_odoo_scayle_token
        )
        self.base_url = "http://{}:{}".format(
            common.HOST, odoo.tools.config["http_port"]
        )
        odoo_response = self.opener.get(
            f"{self.base_url}{order_webhook_url}",
            json=payload,
        )
        self.assertEqual(odoo_response.status_code, 200, "The response must be match.")
        response = json.loads(odoo_response.json().get("result"))
        return response

    def get_payload_for_webhook(
        self,
        warehouses=None,
        products=None,
        from_date=None,
        to_date=None,
        limit=None,
        offset=0,
    ):
        """# T-02331 Generates dynamic payload to cover all the tests for webhook"""
        params = {
            "limit": limit or 10,
            "offset": offset or 0,
        }
        if warehouses:
            params.update({"warehouse_reference_keys": warehouses})
        if products:
            params.update({"product_sku_lst": products})
        if from_date:
            params.update({"from_date": str(from_date)})
        if to_date:
            params.update({"to_date": str(to_date)})
        data = {"params": params}
        return data

    def check_no_response_assertions(self, response, product_count=0):
        """
        #T-02331 Method to check that no response expected, used specially to cover
        the cases for from_date and to_date interval
        """
        response_1 = response.get(self.wh1.warehouse_reference_key, {})
        response_2 = response.get(self.wh2.warehouse_reference_key, {})
        if (
            response_1
            and "total_product_count" not in response_1
            or response_2
            and "total_product_count" not in response_2
        ):
            raise AssertionError(
                "toal_product_count didn't found in the warehouse values!"
            )
        if (
            response_1.get("total_product_count", 0) != product_count
            or response_2.get("total_product_count", 0) != product_count
        ):
            raise AssertionError("No of products and count didn't match!")
        if len(response_1.get("stock_inventory", [])) or len(
            response_2.get("stock_inventory", [])
        ):
            raise AssertionError("Unexpected Response!")

    def check_product_quant_and_inventory_date_webhook(
        self,
        response,
        record_count,
        quantity_dict=None,
        warehouses=None,
        products=None,
    ):
        """#T-02331 Generic method for assertions of webhook"""
        quantity_dict = quantity_dict or {}
        if not warehouses:
            warehouses = [self.wh1, self.wh2]
        if not products:
            products = self.product_skus
        if not isinstance(warehouses, list):
            warehouses = [warehouses]
        if not isinstance(products, list):
            products = [products]
        for wh in warehouses:
            self.assertIn(
                wh.warehouse_reference_key,
                response.keys(),
                "Warehouse Reference Key not found!",
            )
        inventory = response.get(wh.warehouse_reference_key, {}).get(
            "stock_inventory", []
        )
        self.assertEqual(
            len(inventory),
            record_count,
            "Length should be match!",
        )
        for inv in inventory:
            if inv.get("product_sku") not in products:
                raise AssertionError("Unexpected No of products are found")
            quantity = quantity_dict.get(inv.get("product_sku"), 0)
            self.assertEqual(
                inv.get("quantity"), quantity, "Quantity should be the same!"
            )
            self.assertEqual(
                inv.get("sellableQuantity"),
                inv.get("quantity"),
                "Sellable quantity and quantity should be the same",
            )

    def inventory_sws_date_assertions(
        self, old_inv=None, new_inv=None, old_sws=None, new_sws=None, should_match=False
    ):
        """
        #T-02331 Generic method for inventory update date and sws update date
        assertions
        """
        if should_match:
            if old_inv and new_inv:
                if old_inv < new_inv:
                    raise AssertionError("Inventory Update Date should be matched!")
            if old_sws and new_sws:
                if old_sws < new_sws:
                    raise AssertionError("SWS Update Date should be matched!")
        else:
            if old_inv and new_inv:
                if old_inv == new_inv:
                    raise AssertionError("Inventory Update Date should not be matched!")
            if old_sws and new_sws:
                if old_sws == new_sws:
                    raise AssertionError("SWS Update Date should not be matched!")

    def check_quant_and_inventory_date_from_delivery(self, product_dict):
        """
        #T-02331 Method to check the inventory update date assertions with
        webhook response and with decreasing quantity
        """
        from_date = self.from_date - timedelta(days=1)
        to_date = self.from_date + timedelta(days=1)
        for wh in [self.wh1, self.wh2]:
            stock_update_ids_1 = self.test_product_1.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id == wh
            )
            self.assertEqual(
                len(stock_update_ids_1),
                1,
                "Stock Update Date ids has to be present",
            )
            stock_update_ids_2 = self.test_product_2.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id == wh
            )
            self.assertEqual(
                len(stock_update_ids_2),
                1,
                "Stock Update Date ids has to be present",
            )

            inventory_dates_1 = self.test_product_1.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")

            inventory_dates_2 = self.test_product_2.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")
            inventory_update_date_1 = stock_update_ids_1.inventory_update_date
            inventory_update_date_2 = stock_update_ids_2.inventory_update_date

            sws_update_date_1 = stock_update_ids_1.sws_update_date
            sws_update_date_2 = stock_update_ids_2.sws_update_date

            product_1_demand_qty = product_dict.get(
                self.test_product_1.default_code, {}
            ).get("demand_qty", 0)
            product_2_demand_qty = product_dict.get(
                self.test_product_2.default_code, {}
            ).get("demand_qty", 0)
            product_1_expected_qty = product_dict.get(
                self.test_product_1.default_code, {}
            ).get("expected_qty", 0)
            product_2_expected_qty = product_dict.get(
                self.test_product_2.default_code, {}
            ).get("expected_qty", 0)
            partner1 = self.env.ref("base.res_partner_address_15")
            # T-02857 used SUPERUSER_ID as of only superuser (odoobot)
            # writes the is_intercompany.
            partner1.with_user(SUPERUSER_ID).write(
                {
                    "branch_code": "0721",
                    "is_intercompany": True,
                    "shop_entity_id": self.env.ref(
                        "connector_base_ecommerce.shop_entity_fielmann"
                    ),
                },
            )
            sale_order1 = (
                self.env["sale.order"]
                .with_user(SUPERUSER_ID)
                .create(
                    {
                        "partner_id": partner1.id,
                        "warehouse_id": wh.id,
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": self.test_product_1.id,
                                    "product_uom_qty": product_1_demand_qty,
                                    "price_unit": 60.0,
                                },
                            ),
                            (
                                0,
                                0,
                                {
                                    "product_id": self.test_product_2.id,
                                    "product_uom_qty": product_2_demand_qty,
                                    "price_unit": 60.0,
                                },
                            ),
                        ],
                        "partner_revenue_id": partner1.id,
                    }
                )
            )
            # T-02331 We should have to wait atleast for 1 second before updating the
            # inventory update date. It may fail if we don't use time.sleep(1) in
            # case the transaction happens too fast

            self.inventory_sws_date_assertions(
                old_inv=inventory_update_date_1,
                new_inv=stock_update_ids_1.inventory_update_date,
                old_sws=sws_update_date_1,
                new_sws=stock_update_ids_1.sws_update_date,
                should_match=True,
            )
            self.inventory_sws_date_assertions(
                old_inv=inventory_update_date_2,
                new_inv=stock_update_ids_2.inventory_update_date,
                old_sws=sws_update_date_2,
                new_sws=stock_update_ids_2.sws_update_date,
                should_match=True,
            )
            time.sleep(1)
            sale_order1.action_confirm()
            payload = self.get_payload_for_webhook(
                warehouses=[wh.warehouse_reference_key],
                products=self.product_skus,
                from_date=from_date,
                to_date=to_date,
            )

            # To make sure the compute triggered after SO confirmation
            self.test_product_1.stock_quant_ids.flush_recordset()
            self.test_product_2.stock_quant_ids.flush_recordset()
            not_update_inv_dates_1 = self.test_product_1.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")

            not_update_inv_dates_2 = self.test_product_2.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")

            # T-02331 Assertions to ensure that inventory update date
            # only change for the current warehouse.
            self.inventory_sws_date_assertions(
                old_inv=inventory_dates_1[0],
                new_inv=not_update_inv_dates_1[0],
                should_match=True,
            )
            self.inventory_sws_date_assertions(
                old_inv=inventory_dates_2[0],
                new_inv=not_update_inv_dates_2[0],
                should_match=True,
            )

            response = self.process_stock_update_webhook(payload)

            quantity_dict = {
                self.test_product_1.default_code: product_1_expected_qty,
                self.test_product_2.default_code: product_2_expected_qty,
            }
            self.check_product_quant_and_inventory_date_webhook(
                response=response,
                record_count=3,
                quantity_dict=quantity_dict,
                warehouses=[wh],
            )

            updated_inventory_update_date_1 = stock_update_ids_1.inventory_update_date
            updated_inventory_update_date_2 = stock_update_ids_2.inventory_update_date

            sws_no_update_date_1 = stock_update_ids_1.sws_update_date
            sws_no_update_date_2 = stock_update_ids_2.sws_update_date

            self.inventory_sws_date_assertions(
                inventory_update_date_1,
                updated_inventory_update_date_1,
                should_match=False,
            )

            self.inventory_sws_date_assertions(
                old_inv=inventory_update_date_2,
                new_inv=updated_inventory_update_date_2,
                should_match=False,
            )
            self.inventory_sws_date_assertions(
                old_sws=sws_update_date_1,
                new_sws=sws_no_update_date_1,
                should_match=True,
            )

            self.inventory_sws_date_assertions(
                old_sws=sws_update_date_2,
                new_sws=sws_no_update_date_2,
                should_match=True,
            )

            time.sleep(1)
            for move in sale_order1.picking_ids.move_ids:
                move.quantity = move.product_uom_qty
            sale_order1.picking_ids.button_validate()
            self.assertEqual(
                sale_order1.picking_ids.state, "done", "Picking state should be done!"
            )

            self.check_product_quant_and_inventory_date_webhook(
                response=response,
                record_count=3,
                quantity_dict=quantity_dict,
                warehouses=[wh],
            )
            no_update_inventory_date_1 = stock_update_ids_1.inventory_update_date
            no_update_inventory_date_2 = stock_update_ids_2.inventory_update_date

            updated_sws_no_update_date_1 = stock_update_ids_1.sws_update_date
            updated_sws_no_update_date_2 = stock_update_ids_2.sws_update_date

            # T-02331 assertions to make sure that inventory update date is not
            # updated when the outgoing picking is going to be done.
            # as the sellable already updated while confirming the SO it should
            # not affect the inventory update and should match the old value
            # Case: validating Delivery order
            # where src loc. = warehouse output and dest loc. = customer
            self.inventory_sws_date_assertions(
                new_inv=no_update_inventory_date_1,
                old_inv=updated_inventory_update_date_1,
                should_match=True,
            )

            self.inventory_sws_date_assertions(
                new_inv=no_update_inventory_date_2,
                old_inv=updated_inventory_update_date_2,
                should_match=True,
            )

            self.inventory_sws_date_assertions(
                old_sws=sws_no_update_date_1,
                new_sws=updated_sws_no_update_date_1,
                should_match=True,
            )
            self.inventory_sws_date_assertions(
                old_sws=sws_no_update_date_2,
                new_sws=updated_sws_no_update_date_2,
                should_match=True,
            )

    def check_quant_and_inventory_date_from_receipt(
        self,
        product_dict,
    ):
        """
        #T-02331 Method to check the inventory update date assertions with
        webhook response and with increasing quantity
        """
        from_date = self.from_date - timedelta(days=1)
        to_date = self.to_date + timedelta(days=1)
        time.sleep(1)
        for wh in [self.wh1, self.wh2]:
            stock_update_ids_1 = self.test_product_1.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id == wh
            )
            inventory_dates_1 = self.test_product_1.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")

            inventory_dates_2 = self.test_product_2.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")

            self.assertEqual(
                len(stock_update_ids_1),
                1,
                "Stock Update Date ids has to be present",
            )
            stock_update_ids_2 = self.test_product_2.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id == wh
            )
            self.assertEqual(
                len(stock_update_ids_2),
                1,
                "Stock Update Date ids has to be present",
            )
            inventory_update_date_1 = stock_update_ids_1.inventory_update_date
            inventory_update_date_2 = stock_update_ids_2.inventory_update_date

            sws_update_date_1 = stock_update_ids_1.sws_update_date
            sws_update_date_2 = stock_update_ids_2.sws_update_date

            picking_type = self.env["stock.picking.type"].search(
                [("code", "=", "incoming"), ("warehouse_id", "=", wh.id)]
            )
            product_1_demand_qty = product_dict.get(
                self.test_product_1.default_code, {}
            ).get("demand_qty", 0)
            product_2_demand_qty = product_dict.get(
                self.test_product_2.default_code, {}
            ).get("demand_qty", 0)
            product_1_expected_qty = product_dict.get(
                self.test_product_2.default_code, {}
            ).get("expected_qty", 0)
            product_2_expected_qty = product_dict.get(
                self.test_product_2.default_code, {}
            ).get("expected_qty", 0)
            purchase_order1 = self.env["purchase.order"].create(
                {
                    "partner_id": self.env.ref("base.res_partner_address_14").id,
                    "picking_type_id": picking_type.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.test_product_1.id,
                                "product_qty": product_1_demand_qty,
                                "price_unit": 60.0,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "product_id": self.test_product_2.id,
                                "product_qty": product_2_demand_qty,
                                "price_unit": 60.0,
                            },
                        ),
                    ],
                }
            )
            time.sleep(1)
            purchase_order1.button_confirm()
            # T-02331 Assertions that inventory update date and sws update date is not
            # changed when the receipt is created
            inventory_no_update_date_1 = stock_update_ids_1.inventory_update_date
            inventory_no_update_date_2 = stock_update_ids_2.inventory_update_date

            sws_no_update_date_1 = stock_update_ids_1.sws_update_date
            sws_no_update_date_2 = stock_update_ids_2.sws_update_date
            self.inventory_sws_date_assertions(
                inventory_update_date_1,
                inventory_no_update_date_1,
                sws_update_date_1,
                sws_no_update_date_1,
                should_match=True,
            )
            self.inventory_sws_date_assertions(
                inventory_update_date_2,
                inventory_no_update_date_2,
                sws_update_date_2,
                sws_no_update_date_2,
                should_match=True,
            )

            # T-02331 Assertions for the webhook, that quantity has not been updated
            # when the receipt is created
            payload = self.get_payload_for_webhook(
                warehouses=[wh.warehouse_reference_key],
                products=self.product_skus,
                from_date=from_date,
                to_date=to_date,
            )
            response = self.process_stock_update_webhook(payload)

            self.check_product_quant_and_inventory_date_webhook(
                response=response, record_count=3, warehouses=[wh]
            )

            # T-02331 We should have to wait atleast for 1 second before updating the
            # inventory update date. It may fail if we don't use time.sleep(1) in
            # case the transaction happens too fast
            time.sleep(1)
            for move in purchase_order1.picking_ids.move_ids:
                move.quantity = move.product_uom_qty
            purchase_order1.picking_ids.button_validate()

            # To make sure the compute triggered after picking validate
            self.test_product_1.stock_quant_ids.flush_recordset()
            self.test_product_2.stock_quant_ids.flush_recordset()
            self.assertEqual(
                purchase_order1.picking_ids.state,
                "done",
                "Picking state should be done!",
            )

            not_update_inv_dates_1 = self.test_product_1.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")

            not_update_inv_dates_2 = self.test_product_2.stock_update_date_ids.filtered(
                lambda inv, wh=wh: inv.warehouse_id
                in {self.wh1, self.wh2}.difference(set(wh))
            ).mapped("inventory_update_date")

            # T-02331 Assertions to ensure that inventory update date
            # only change for the current warehouse.
            self.inventory_sws_date_assertions(
                old_inv=inventory_dates_1[0],
                new_inv=not_update_inv_dates_1[0],
                should_match=True,
            )
            self.inventory_sws_date_assertions(
                old_inv=inventory_dates_2[0],
                new_inv=not_update_inv_dates_2[0],
                should_match=True,
            )

            updated_inventory_update_date_1 = stock_update_ids_1.inventory_update_date
            updated_inventory_update_date_2 = stock_update_ids_2.inventory_update_date

            updated_sws_update_date_1 = stock_update_ids_1.sws_update_date
            updated_sws_update_date_2 = stock_update_ids_2.sws_update_date

            self.inventory_sws_date_assertions(
                old_inv=inventory_update_date_1,
                new_inv=updated_inventory_update_date_1,
                should_match=False,
            )
            self.inventory_sws_date_assertions(
                old_inv=inventory_update_date_2,
                new_inv=updated_inventory_update_date_2,
                should_match=False,
            )

            self.inventory_sws_date_assertions(
                old_sws=sws_no_update_date_1,
                new_sws=updated_sws_update_date_1,
                should_match=True,
            )
            self.inventory_sws_date_assertions(
                old_sws=sws_no_update_date_2,
                new_sws=updated_sws_update_date_2,
                should_match=True,
            )

            response = self.process_stock_update_webhook(payload)

            self.check_product_quant_and_inventory_date_webhook(
                response=response,
                quantity_dict={
                    self.test_product_1.default_code: product_1_expected_qty,
                    self.test_product_2.default_code: product_2_expected_qty,
                },
                record_count=3,
                warehouses=[wh],
            )

    def asserts_for_sws_logic(
        self,
        product_variant,
        eshop_sws=False,
        is_orderable=False,
    ):
        """
        NEW METHOD : [# T-02463 Added new method for assertions for eshop_sws and
        is_orderable]
        """
        if not eshop_sws:
            self.assertFalse(product_variant.eshop_sws, "Scayle SWS should be False")
        else:
            self.assertTrue(product_variant.eshop_sws, "Scayle SWS should be True")
        if not is_orderable:
            self.assertFalse(
                product_variant.is_orderable, "Is Orderable should be False"
            )
        else:
            self.assertTrue(product_variant.is_orderable, "Is Orderable should be True")

    def check_sellable_quantity(self, sellable_quantity, default_code):
        """#T-02583 Generic Method: send response to webhook"""
        sellable_quantity = sellable_quantity or 0
        response = self.get_payload_for_webhook(
            warehouses=[
                self.wh1.warehouse_reference_key,
            ],
            products=[default_code],
        )
        res = self.process_stock_update_webhook(response)
        qty = (
            res.get(self.wh1.warehouse_reference_key, {})
            .get("stock_inventory")[-1]
            .get("sellableQuantity")
        )
        self.assertEqual(
            qty,
            sellable_quantity,
            "Sellable Quantity should be matched!!",
        )

    def check_sellable_quantity_for_unified_warehouse(
        self, sellable_quantity, default_code
    ):
        """#T-02849 New/Test Method: To check unified warehouse quantity for wh1"""
        self.scayle_backend.company_id.eshop_unified_warehouse_id = self.wh1
        response = self.get_payload_for_webhook(
            warehouses=[
                self.wh2.warehouse_reference_key,
                self.wh1.warehouse_reference_key,
            ],
            products=[default_code],
        )
        res = self.process_stock_update_webhook(response)
        qty = (
            res.get(self.wh1.warehouse_reference_key, {})
            .get("stock_inventory")[-1]
            .get("sellableQuantity")
        )
        self.assertEqual(
            qty,
            sellable_quantity,
            "Sellable Quantity should be matched!!",
        )

    def check_no_unified_key_in_request(self, default_code):
        """
        #T-02849 New/Test Method: To check response when unified warehouse
        reference_key is not send from the request.
        """
        self.scayle_backend.company_id.eshop_unified_warehouse_id = self.wh1
        response = self.get_payload_for_webhook(
            warehouses=[self.wh2.warehouse_reference_key],
            products=[default_code],
        )
        res = self.process_stock_update_webhook(response)
        res = res.get(self.wh2.warehouse_reference_key, {})

        self.assertDictEqual(
            res, {}, "Expected empty response when unified warehouse key is missing."
        )

    def check_no_product_sku_in_request(self, sellable_quantity, updated_product_sku):
        """
        #T-02849 New/Test Method: To check response when no product SKU is not send
        from the request.
        """
        self.scayle_backend.company_id.eshop_unified_warehouse_id = self.wh1
        response = self.get_payload_for_webhook(
            warehouses=[
                self.wh2.warehouse_reference_key,
                self.wh1.warehouse_reference_key,
            ]
        )
        res = self.process_stock_update_webhook(response)
        stock_inventory = res.get(self.wh1.warehouse_reference_key, {}).get(
            "stock_inventory", []
        )
        matching_product = next(
            (
                item
                for item in stock_inventory
                if item.get("product_sku") == updated_product_sku
            ),
            None,
        )
        self.assertEqual(
            matching_product.get("sellableQuantity"),
            sellable_quantity,
            "Sellable Quantity should be matched!!",
        )

    def check_from_date_condition(
        self, from_date, sellable_quantity, updated_product_sku
    ):
        """
        #T-02849 New/Test Method: To check response when from_date is send
        from the request.
        """
        self.scayle_backend.company_id.eshop_unified_warehouse_id = self.wh1
        response = self.get_payload_for_webhook(
            warehouses=[
                self.wh2.warehouse_reference_key,
                self.wh1.warehouse_reference_key,
            ],
            from_date=from_date,
        )
        res = self.process_stock_update_webhook(response)
        stock_inventory = res.get(self.wh1.warehouse_reference_key, {}).get(
            "stock_inventory", []
        )
        # Iterating over the stock inventory records to check the dates
        for record in stock_inventory:
            changed_at_str = record.get("changedAt")
            sws_update_date_str = record.get("sws_update_date")

            # Convert the date strings to datetime objects
            changed_at = (
                datetime.strptime(changed_at_str, "%m/%d/%Y, %H:%M:%S")
                if changed_at_str
                else None
            )
            sws_update_date = (
                datetime.strptime(sws_update_date_str, "%m/%d/%Y, %H:%M:%S")
                if sws_update_date_str
                else None
            )

            # Perform the assertions for both 'changedAt' and 'sws_update_date'
            if changed_at:
                self.assertGreaterEqual(
                    changed_at,
                    from_date,
                    f"""changedAt for product SKU {record.get('product_sku')} is less
                    than from_date!""",
                )
            if sws_update_date:
                self.assertGreaterEqual(
                    sws_update_date,
                    from_date,
                    f"""sws_update_date for product SKU {record.get('product_sku')} is
                    less than from_date!""",
                )
        matching_product = next(
            (
                item
                for item in stock_inventory
                if item.get("product_sku") == updated_product_sku
            ),
            None,
        )
        self.assertEqual(
            matching_product.get("sellableQuantity"),
            sellable_quantity,
            "Sellable Quantity should be matched!!",
        )

    def check_to_date_condition(self, to_date, sellable_quantity, updated_product_sku):
        """
        #T-02849 New/Test Method: To check response when to_date is send
        from the request.
        """
        self.scayle_backend.company_id.eshop_unified_warehouse_id = self.wh1
        response = self.get_payload_for_webhook(
            warehouses=[
                self.wh2.warehouse_reference_key,
                self.wh1.warehouse_reference_key,
            ],
            to_date=to_date,
        )
        res = self.process_stock_update_webhook(response)
        # Extracting the stock inventory for the warehouse

        stock_inventory = res.get(self.wh1.warehouse_reference_key, {}).get(
            "stock_inventory", []
        )

        # Iterating over the stock inventory records to check the dates
        for record in stock_inventory:
            product = self.env["product.product"].search(
                [("default_code", "=", record.get("product_sku"))]
            )
            self.assertEqual(
                product.free_qty,
                record.get("sellableQuantity"),
                "Free Quantity of product is not matched!!",
            )
            changed_at_str = record.get("changedAt")
            sws_update_date_str = record.get("sws_update_date")

            # Convert the date strings to datetime objects
            changed_at = (
                datetime.strptime(changed_at_str, "%m/%d/%Y, %H:%M:%S")
                if changed_at_str
                else None
            )
            sws_update_date = (
                datetime.strptime(sws_update_date_str, "%m/%d/%Y, %H:%M:%S")
                if sws_update_date_str
                else None
            )

            # Perform the assertions for both 'changedAt' and 'sws_update_date'
            if changed_at:
                self.assertLessEqual(
                    changed_at,
                    to_date,
                    f"""changedAt for product SKU {record.get('product_sku')} is greater
                    than to_date!""",
                )
            if sws_update_date:
                self.assertLessEqual(
                    sws_update_date,
                    to_date,
                    f"""sws_update_date for product SKU {record.get('product_sku')} is
                    greater than to_date!""",
                )
        matching_product = next(
            (
                item
                for item in stock_inventory
                if item.get("product_sku") == updated_product_sku
            ),
            None,
        )
        self.assertEqual(
            matching_product.get("sellableQuantity"),
            sellable_quantity,
            "Sellable Quantity should be matched!!",
        )

    def set_distribution_percentage(
        self,
        magento_percentage,
        scayle_percentage,
        product_category=None,
        branded_product=None,
    ):
        """
        #T-02583 Generic Method: Configuration to create scayle stock ratio
        based on the parameter value.
        """

        product_category = product_category or self.product_category

        def _prepare_ratio_vals(brand=None):
            """T-02863: helper method for prepare ratio vals"""
            values = [
                {
                    "backend_group_id": self.magento_group.id,
                    "percentage": magento_percentage,
                },
                {
                    "backend_group_id": self.scayle_group.id,
                    "percentage": scayle_percentage,
                },
            ]
            if brand:
                for value in values:
                    value["product_brand_id"] = brand.id
            return [(0, 0, value) for value in values]

        # T-02863 if branded product found update brand ratios.
        if branded_product:
            product_category.eshop_brand_ratio_ids.unlink()
            product_category.write(
                {"eshop_brand_ratio_ids": _prepare_ratio_vals(branded_product)}
            )
        # T-02863 update eshop stock ratios.
        product_category.eshop_stock_ratio_ids.unlink()
        product_category.write({"eshop_stock_ratio_ids": _prepare_ratio_vals()})

    def set_route_configuration(self):
        """# T-02849 Added method to set the configuration."""
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        grp_multi_routes = self.env.ref("stock.group_adv_location")
        self.env.user.write(
            {"groups_id": [(4, grp_multi_loc.id), (4, grp_multi_routes.id)]}
        )  # T-02849 write group ids of locations
        self.mto_route = self.env.ref("stock.route_warehouse0_mto")
        self.mto_route.write({"active": True})
        self.warehouseObj = self.env["stock.warehouse"]
        self.mrp_frame_warehouse = self.warehouseObj.create(
            {
                "name": "FRAME WAREHOUSE(MRP)",
                "code": "FRAME",
                "warehouse_reference_key": "FRAME",
            }
        )  # T-02849 warehouse
        self.us_country = self.env.ref("base.us")  # T-02849 us_country
        self.productCategObj = self.env["product.category"]
        self.finish_category = self.productCategObj.create(
            {
                "name": "Finished Product",
                "eshop_skip_inventory_update": True,
                "route_ids": [(6, 0, self.mrp_frame_warehouse.delivery_route_id.ids)],
            }
        )
        self.mrp_frame_warehouse.wh_output_stock_loc_id.write({"active": True})
        self.company_mrp = self.env.ref("base.main_company")
        # T-02849 - creating routes for creation of Mrp production.
        self.customer_location = self.env.ref("stock.stock_location_customers")
        self.loc_dest = self.mrp_frame_warehouse.wh_output_stock_loc_id
        self.route = self.env["stock.route"].create(
            {
                "name": "2 steps ship",
                "company_id": self.company_mrp.id,
                "product_categ_selectable": True,
                "warehouse_selectable": True,
                "sale_selectable": True,
                "warehouse_ids": [(6, 0, self.mrp_frame_warehouse.ids)],
                "rule_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "STOCK TO CUSTOMERS",
                            "picking_type_id": self.mrp_frame_warehouse.pick_type_id.id,
                            "location_src_id": self.mrp_frame_warehouse.lot_stock_id.id,
                            "location_dest_id": self.loc_dest.id,
                            "action": "pull",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "OUT TO CUSTOMERS",
                            "picking_type_id": self.mrp_frame_warehouse.out_type_id.id,
                            "location_dest_id": self.customer_location.id,
                            "location_src_id": self.loc_dest.id,
                            "procure_method": "make_to_order",
                            "propagate_carrier": True,
                            "action": "pull",
                        },
                    ),
                ],
            }
        )
        self.stock_to_prod_rule = self.mto_route.rule_ids.filtered(
            lambda rule: rule.warehouse_id == self.mrp_frame_warehouse
        )
        self.stock_to_prod_rule.write(
            {"location_src_id": self.mrp_frame_warehouse.lot_stock_id.id}
        )
        self.company_mrp.write(
            {
                "allow_mrp_flow": True,
                "finished_product_category_id": self.finish_category.id,
                "finished_product_extra_weight": 2.0,
            }
        )  # T-02849 -mrp company
        self.picking_type_internal = self.env.ref(
            "stock.picking_type_internal"
        )  # T-02849 - picking type internal
        self.partner_1 = self.env["res.partner"].create(
            {
                "name": "Test Partner 1",
                "branch_code": "ABC1234",
                "shop_entity_id": self.shop_entity.id,
                "country_id": self.us_country.id,
                "is_intercompany": True,
            }
        )
        self.env.user.write(
            {"allowed_intercompany_partner_ids": [(4, self.partner_1.id)]}
        )
        self.delivery_product_category = self.env.ref(
            "delivery.product_category_deliveries"
        )

    def set_branch_code_shop_entity(self, partner, branch_code=None, shop_entity=None):
        """#T-02933 New/Generic Method: TO set the branch code and shop entity id"""
        shop_entity = shop_entity or self.env.ref(
            "connector_base_ecommerce.shop_entity_fielmann"
        )
        partner.write(
            {"branch_code": branch_code or "BR0001", "shop_entity_id": shop_entity.id}
        )


class ScayleTestMRPCases(MRPWarehouseCases):
    @classmethod
    def setUpClass(cls):
        """#T-02933 configurations for the scayle backend with MRP"""
        super().setUpClass()
        cls.de_country = cls.env["res.country"].search([("code", "=", "DE")])
        cls.de_currency = cls.env.ref("base.EUR")
        cls.de_currency.active = True
        cls.de_default_pricelist = cls.env["product.pricelist"].create(
            {"name": "Default DE Pricelist", "currency_id": cls.de_currency.id}
        )
        delivery_carrier_categ = cls.env.ref("delivery.product_category_deliveries")
        deliver_product = cls.env["product.product"].create(
            {
                "name": "Demo Shipping Method DE",
                "type": "service",
                "categ_id": delivery_carrier_categ.id,
            }
        )  # T-02933 delivery product
        # T-02933 delivery carriers
        cls.cod_delivery_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "DE Carrier COD",
                "product_id": deliver_product.id,
                "eshop_carrier_code": "POST_DE",
                "shipment_options": "home_cod",
            }
        )
        cls.hd_delivery_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "DE Carrier HD",
                "product_id": deliver_product.id,
                "eshop_carrier_code": "EXPRESS",
                "shipment_options": "home_delivery",
                "is_express_carrier": True,
            }
        )
        cls.shop_entity_fielmann = cls.env.ref(
            "connector_base_ecommerce.shop_entity_fielmann"
        )
        cls.de_scayle_shop_partner = cls.env["res.partner"].create(
            {
                "name": "DE",
                "is_intercompany": True,
            }
        )  # T-02933 scayle partner
        de_sales_team = cls.env["crm.team"].create(
            {
                "name": cls.de_scayle_shop_partner.name,
                "company_id": cls.company_mrp.id,
            }
        )
        cls.de_scayle_shop = cls.env["scayle.shop"].create(
            {
                "name": cls.de_scayle_shop_partner.name,
                "partner_id": cls.de_scayle_shop_partner.id,
                "sales_team_id": de_sales_team.id,
            }
        )

        cls.set_branch_code_shop_entity(
            cls,
            cls.de_scayle_shop_partner,
            branch_code="0189",
        )
        cls.test_backend_group_access_token = "52d1ce46-af59-468d-91a2-a06f0aa54e62"
        cls.scayle_group_with_mrp = cls.env["backend.group"].create(
            {
                "name": "Scayle Group",
                "backend_group_access_token": "52d1ce46-af59-468d-91a2-a06f0aa54e61",
                "test_backend_group_access_token": cls.test_backend_group_access_token,
            }
        )
        # T-02933 - scayle backend with MRP
        cls.de_scayle_backend_mrp = cls.env["scayle.backend"].create(
            {
                "name": "Test DE Scayle",
                "version": "v1",
                "test_location": "test",
                "shop_key": "fa",
                "country_id": cls.de_country.id,
                "test_token": "test",
                "warehouse_ids": [(6, 0, [cls.mrp_frame_warehouse.id])],
                "default_pricelist_id": cls.de_default_pricelist.id,
                "test_mode": True,
                "sale_prefix": "SCAYLE-DE",
                "test_odoo_scayle_token": "52d1ce46-af59-468d-91a2-a06f0aa54e61",
                "company_id": cls.company_mrp.id,
                "code": "DE",
                "shop_id": "10005",
                "scayle_shop_id": cls.de_scayle_shop.id,
                "backend_group_id": cls.scayle_group_with_mrp.id,
                "cod_payment_method": "de_cod",
                "auto_confirm_order": True,
            }
        )

    def set_branch_code_shop_entity(self, partner, branch_code=None, shop_entity=None):
        """#T-02933 New/Generic Method: TO set the branch code and shop entity id"""
        shop_entity = shop_entity or self.env.ref(
            "connector_base_ecommerce.shop_entity_fielmann"
        )
        partner.write(
            {"branch_code": branch_code or "BR0001", "shop_entity_id": shop_entity.id}
        )

    def process_order_creation(self):
        """#T-02933 Called webhook for sale order"""
        self.env["scayle.sale.order"].import_record(
            self.de_scayle_backend_mrp,
            external_id="66254693892148",
            data=frame_2_regular_1_data,
        )
        scayle_order = self.env["scayle.sale.order"].search(
            [("external_id", "=", "66254693892148")]
        )
        sequence = 1
        for line in scayle_order.order_line.filtered(
            lambda line: line.is_prescription_line
        ).sorted("create_date"):
            self.assertEqual(
                line.sequence_number,
                sequence,
                f"Sequence Number {sequence} should match",
            )
            self.assertTrue(line.frame_product_id, "Frame Product Should Exist")
            finished_product = line.product_id
            finished_product_default_code = finished_product.default_code
            removed_prefix_default_code = finished_product.get_external_id_from_sku(
                finished_product_default_code
            )
            finished_product_barcode = finished_product.get_external_id_from_sku(
                finished_product.barcode
            )
            self.assertEqual(
                removed_prefix_default_code,
                line.scayle_bind_ids[0].external_id,
            )
            self.assertEqual(
                finished_product_barcode, line.scayle_bind_ids[0].external_id
            )
            self.assertEqual(finished_product.categ_id, self.finish_category)
            sequence += 1
        return scayle_order
