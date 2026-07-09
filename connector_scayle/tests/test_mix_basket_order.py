from odoo.tests.common import users

from .common import ScayleTestCases


class TestMixedBasket(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """#T-02256 Configurations for mixed basket order."""
        super().setUpClass()

    @users("inventory_manager")
    def test_mixed_basket(self):
        """
        New Method: Added method to check functionality of mixed basket order with
        multiple delivery order and also traversal of fields. # T-02556
        """
        # Added new list of item as to add item with different WH. # T-02556.
        # T-02857 check current user as inventory manager.
        self.assertEqual(
            self.env.user,
            self.inventory_manager,
            "Current User is not the Inventory Manager",
        )
        updated_item_list = [
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
                "shippingWarehouseReferenceKey": "WH2",
                "tax": 23,
                "taxAmount": 7833,
                "vendorReferenceKey": None,
                "vendorSize": None,
                "warehouseReferenceKey": "WH2",
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
        ]
        self.scayle_order_payload.update({"items": updated_item_list, "id": 15175})
        self.external_id = self.scayle_order_payload.get("orderId")
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=self.external_id,
            data=self.scayle_order_payload,
        )

        self.sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", self.external_id)]
        )
        self.sale_binding.odoo_id.action_confirm()
        so_binding = self.sale_binding
        so = so_binding.odoo_id
        order_line = so.order_line
        self.assertEqual(
            len(so.picking_ids.ids),
            2,
            "There should be only 2 pickings for mixed basket Order.",
        )
        self.assertEqual(
            order_line[0].route_id.name,
            "Warehouse1: Deliver in 1 step (ship)",
            "Route did not match please check!!",
        )
        self.assertEqual(
            order_line[1].route_id.name,
            "Warehouse2: Deliver in 1 step (ship)",
            "Route did not match please check!!",
        )
        p1, p2 = so.picking_ids
        p1.action_assign()
        p2.action_assign()
        p1.move_ids.quantity = 2
        p2.move_ids.quantity = 1
        p1.with_context(auto_shipment=True).button_validate()
        p2.with_context(auto_shipment=True).button_validate()
        self.assertEqual(len(so.invoice_ids.ids), 2, "Two Invoices should be created!!")
        self.assertEqual(
            so.partner_revenue_id.branch_code,
            "0722",
            "Revenue Partner did not mapped properly!",
        )
        self.assertEqual(
            so.invoice_ids[0].partner_revenue_id,
            so.partner_revenue_id,
            "Revenue Partner should be matched!!",
        )
        self.assertEqual(
            so.invoice_ids[1].partner_revenue_id,
            so.partner_revenue_id,
            "Revenue Partner should be matched!!",
        )
