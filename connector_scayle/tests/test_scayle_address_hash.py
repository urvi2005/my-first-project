from os.path import dirname, join

from vcr import VCR

from odoo.exceptions import ValidationError

from .common import ScayleTestCases

recorder = VCR(
    cassette_library_dir=join(dirname(__file__), "fixtures/cassettes"),
    decode_compressed_response=True,
    filter_headers=["Authorization"],
    path_transformer=VCR.ensure_suffix(".yaml"),
    record_mode="once",
)


class TestScayleAddressHash(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """Configurations for Scayle Address Hash. # T-02816"""
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
        cls.import_first_order()

    @classmethod
    def import_first_order(cls):
        """
        New Method: import the order to prepare partner and hash values.#T-02816
        """
        cls.binding_model.import_record(
            backend=cls.scayle_backend,
            external_id=cls.scayle_order_payload.get("orderId"),
            data=cls.scayle_order_payload,
        )
        sale_binding = cls.binding_model.sudo().search(
            [("external_id", "=", cls.scayle_order_payload.get("orderId"))]
        )
        cls.sale_order = sale_binding.odoo_id
        cls.initial_partner = cls.sale_order.partner_shipping_id
        cls.initial_hash = cls.initial_partner.scayle_bind_ids.address_hash_code

    def test_partner_created_on_first_import(self):
        """
        New Method: Verify shipping partner is created correctly during first import.
        #T-02816
        """
        self.assertTrue(
            self.initial_partner,
            "Expected shipping partner to be set on the sale order.",
        )
        self.assertEqual(
            self.initial_partner.name, "Doris Oliver", "Partner name should match."
        )
        self.assertEqual(
            self.initial_hash,
            "58c9cc93fd741c534c0dcc2acefe0473464726d756c64fa931815d37ab667f7ba09f9e21805ce75e0414282651ad407fd6a0cd97cccfbe11be535edd129ea1a1",
            "Partner hash should match.",
        )

    def test_partner_not_updated_on_duplicate_hash(self):
        """
        New Method: Ensure the partner is reused when hash is unchanged.#T-02816
        """
        self.scayle_order_payload["orderId"] = "99110902"
        self.scayle_order_payload["items"][0]["orderItemId"] = "2968652"
        self.scayle_order_payload["items"][1]["orderItemId"] = "2968653"
        self.scayle_order_payload["items"][2]["orderItemId"] = "2968654"
        self.scayle_order_payload["orderReferenceKey"] = "fapl-10006-99110902"
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.scayle_order_payload.get("orderId"),
            data=self.scayle_order_payload,
        )

        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.scayle_order_payload.get("orderId"))]
        )
        sale_order = sale_binding.odoo_id
        reused_partner = sale_order.partner_shipping_id
        reused_hash = reused_partner.scayle_bind_ids.address_hash_code
        self.assertEqual(
            self.initial_partner, reused_partner, "Partner should remain unchanged."
        )
        self.assertEqual(
            self.initial_hash, reused_hash, "Hash should remain unchanged."
        )
        # Hash code should change when partner address is manually updated.
        reused_partner.city = "New city"
        new_hash = reused_partner.scayle_bind_ids.address_hash_code
        self.assertEqual(
            new_hash,
            "45aa091a9a9bf1d3d6065271b65fb5f5600d9bc0b17539db4b074a9974e13bcb088a138d0b0303b174290d2283b5d8a96ead81fee9bd212ef436ef3aad417092",
            "Partner hash should match.",
        )
        self.assertNotEqual(
            self.initial_hash,
            new_hash,
            "Hash code should change when partner address is manually updated.",
        )

    def test_partner_updated_on_address_change(self):
        """
        New Method: New partner is created when if shipping address changes.#T-02816
        """
        self.scayle_order_payload["orderId"] = "99110903"
        self.scayle_order_payload["items"][0]["orderItemId"] = "2968655"
        self.scayle_order_payload["items"][1]["orderItemId"] = "2968656"
        self.scayle_order_payload["items"][2]["orderItemId"] = "2968657"
        self.scayle_order_payload["orderReferenceKey"] = "fapl-10006-99110903"

        # Modify the address
        self.scayle_order_payload["addresses"]["shipping"]["city"] = "New City"

        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.scayle_order_payload["orderId"],
            data=self.scayle_order_payload,
        )
        updated_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.scayle_order_payload["orderId"])]
        )
        updated_order = updated_binding.odoo_id
        updated_partner = updated_order.partner_shipping_id
        updated_hash = updated_partner.scayle_bind_ids.address_hash_code
        self.assertNotEqual(
            self.initial_partner,
            updated_partner,
            "A new partner should be created when the address changes.",
        )
        self.assertNotEqual(
            self.initial_hash,
            updated_hash,
            "Hash code should change when the address changes.",
        )

    def test_validation_for_non_connector_manager(self):
        """
        New Method: Raise validation if partner information is modified and
        user is not connector mananger. T-02816
        """

        # Create a restricted user (not connector manager)
        user = self.env["res.users"].create(
            {
                "name": "Non Connector Manager",
                "login": "non_connector_manager",
                "email": "noncm@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "restrict_partner_address.by_all", True
        )
        with self.assertRaises(ValidationError):
            self.initial_partner.with_user(user).write({"city": "Los Angeles"})
