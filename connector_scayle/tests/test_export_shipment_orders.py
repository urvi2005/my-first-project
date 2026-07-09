from odoo.tests.common import users

from odoo.addons.queue_job.tests.common import trap_jobs

from .common import ScayleTestCases, recorder


class TestShipmentExport(ScayleTestCases):
    @classmethod
    def setUpClass(cls):
        """#T-02250 Configurations for Shipment Order Export"""
        super().setUpClass()
        cls.external_id = cls.scayle_order_payload.get("orderId")
        cls.binding_model.import_record(
            backend=cls.scayle_backend,
            external_id=cls.external_id,
            data=cls.scayle_order_payload,
        )

        cls.sale_binding = cls.binding_model.sudo().search(
            [("external_id", "=", cls.external_id)]
        )
        cls.sale_binding.odoo_id.action_confirm()
        picking = cls.sale_binding.picking_ids[0]
        picking.write({"carrier_tracking_ref": "POST_AT"})
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.with_context(auto_shipment=True).button_validate()
        with recorder.use_cassette("export_sale_order"):
            cls.sale_binding.odoo_id.export_shipment_orders()

    @users("sale_manager_and_inventory_manager")
    def test_shipment_order_binding_creation(self):
        """#T-02660 Assert shipment order binding creation."""
        self.assertEqual(len(self.sale_binding), 1, "Order Binding is not Created")

    @users("sale_manager_and_inventory_manager")
    def test_shipment_order_assertions(self):
        """#T-02250 assertions for shipment order"""
        so_binding = self.sale_binding
        so = so_binding.odoo_id
        order_line = so.order_line
        self.assertEqual(so.state, "sale", "State must be sale!")

        self.assertEqual(len(order_line), 2, "Length should be 2")
        # T-02250 Added same product in 2 order line to cover the merge line method.
        self.assertEqual(len(order_line.scayle_bind_ids), 3, "Length should be 3")
        line0 = order_line[0]
        line1 = order_line[1]
        prod1 = so.order_line.mapped("product_id")[0]
        prod2 = so.order_line.mapped("product_id")[1]
        scayle_order_product_1 = self.env.ref("connector_scayle.demo_product_1")
        scayle_order_product_2 = self.env.ref("connector_scayle.demo_product_2")
        self.assertEqual(
            prod1.name, scayle_order_product_1.name, "Product name should be matched!"
        )
        self.assertEqual(
            prod1.default_code, "1022643", "Product SKU should be matched!"
        )
        self.assertEqual(
            prod2.name, scayle_order_product_2.name, "Product name should be matched!"
        )
        self.assertEqual(prod2.default_code, "738854", "Product SKU should be matched!")

        self.assertEqual(
            len(line0.scayle_bind_ids), 2, "Length of binding should be 2!"
        )
        self.assertEqual(
            len(line1.scayle_bind_ids), 1, "Length of binding should be 1!"
        )
        self.assertEqual(
            line0.product_uom_qty, 2, "Unexpected product quantity received!"
        )
        self.assertEqual(
            line1.product_uom_qty, 1, "Unexpected product quantity received!"
        )
        self.assertEqual(so.eshop_shipment_status, "full_shipment")
        for line in order_line:
            self.assertEqual(
                line.eshop_shipment_status,
                "full_shipment",
                "Scayle shipment status must be full_shipment",
            )

        # customer = so.partner_id
        # self.assertEqual(len(customer.scayle_bind_ids), 1, "Binding must be exist!")
        self.assertEqual(
            so.partner_invoice_id,
            self.at_scayle_shop.partner_id,
            "Scayle Shop Partner and Invoice partner should be same!",
        )
        self.assertEqual(
            so.partner_id,
            self.at_scayle_shop.partner_id,
            "Customer and scayle shop partner should be same!",
        )
        self.assertEqual(
            so.partner_id.country_id,
            self.at_scayle_shop.partner_id.country_id,
            "CountryCode should be same as selected in scayle shop!",
        )
        self.assertEqual(
            so.partner_shipping_id.street,
            "43 Untere Neugasse",
            "Street hould be matched",
        )
        self.assertEqual(
            so.partner_shipping_id.zip, "3281", "ZipCode should be matched!"
        )

    @users("sale_manager_and_inventory_manager")
    def test_export_binding_with_different_data_type(self):
        """#T-02583 New/Test Method: TO check string is supported."""
        external_id = "ecommmerce99110901"
        scayle_payload = self.scayle_order_payload
        scayle_payload.update(
            {
                "orderId": external_id,
                "orderReferenceKey": "fapl-10006-ecommmerce99110901",
                "id": "11111",
            }
        )
        for item in scayle_payload["items"]:
            item["orderItemId"] = "N" + str(item["orderItemId"])
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=external_id,
            data=scayle_payload,
        )

        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", external_id)]
        )
        self.assertEqual(len(sale_binding), 1, "Order Binding is not Created")
        sale_binding.odoo_id.action_confirm()
        picking = sale_binding.picking_ids[0]
        picking.write({"carrier_tracking_ref": "POST_AT"})
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.with_context(auto_shipment=True).button_validate()
        with recorder.use_cassette("export_sale_order"):
            sale_binding.odoo_id.export_shipment_orders()
        # first history is of import(from scayle), so picked up the second one.
        data_history = sale_binding.api_payload_history_ids[-1].value
        self.assertEqual(
            external_id, data_history["orderId"], "Binding External ID Should match!"
        )
        self.assertEqual(
            type(external_id),
            type(data_history["orderId"]),
            "The data type of import/export Should match!",
        )
        for item in data_history["items"]:
            self.assertEqual(
                type(item["orderItemId"]),
                str,
                "The data type of import/export Should match!",
            )

    @users("sale_manager_and_inventory_manager")
    def test_cancel_binding_with_different_data_type(self):
        """#T-02583 New/Test Method: TO check string is supported."""
        external_id = "ecommmerce99110901"
        scayle_payload = self.scayle_order_payload
        scayle_payload.update(
            {
                "orderId": external_id,
                "orderReferenceKey": "fapl-10006-ecommmerce99110901",
                "id": "11111",
            }
        )
        for item in scayle_payload["items"]:
            item["orderItemId"] = "N" + str(item["orderItemId"])
        self.binding_model.import_record(
            backend=self.scayle_backend,
            external_id=external_id,
            data=scayle_payload,
        )

        sale_binding = self.binding_model.sudo().search(
            [("external_id", "=", external_id)]
        )
        self.assertEqual(len(sale_binding), 1, "Order Binding is not Created")
        sale_order = sale_binding.odoo_id
        sale_order.action_confirm()
        picking = sale_order.picking_ids[0]
        picking.write({"carrier_tracking_ref": "POST_AT"})
        sale_order._compute_scayle_sale_order_line()
        self.assertEqual(
            sale_order.scayle_bind_ids.eshop_cancel_status, "not_cancelled", ""
        )
        with trap_jobs() as trap:
            sale_order.with_context(disable_cancel_warning=True).action_cancel()
            trap.assert_jobs_count(1)
            with recorder.use_cassette("export_cancel_item"):
                trap.perform_enqueued_jobs()

        self.assertEqual(
            sale_order.scayle_bind_ids.eshop_cancel_status, "cancelled", ""
        )
        # first history is of import(from scayle), so picked up the second one.
        data_history = sale_binding.api_payload_history_ids[-1].value
        self.assertEqual(
            external_id, data_history["orderId"], "Binding External ID Should match!"
        )
        self.assertEqual(
            type(external_id),
            type(data_history["orderId"]),
            "The data type of import/export Should match!",
        )
        for item in data_history["items"]:
            self.assertEqual(
                type(item["orderItemId"]),
                str,
                "The data type of import/export Should match!",
            )
