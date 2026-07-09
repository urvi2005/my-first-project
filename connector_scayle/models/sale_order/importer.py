import logging

from markupsafe import Markup

from odoo import SUPERUSER_ID, _
from odoo.exceptions import ValidationError
from odoo.osv import expression

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping
from odoo.addons.connector.exception import InvalidDataError, MappingError
from odoo.addons.connector_settings.components.misc import date_parser

_logger = logging.getLogger(__name__)


class SaleOrderImportMapper(Component):
    _name = "scayle.sale.order.import.mapper"
    _inherit = "scayle.import.mapper"
    _apply_on = "scayle.sale.order"

    direct = [
        ("orderId", "external_id"),
    ]

    @mapping
    def aa_setup_options(self, record):
        """
        Payload structure like {"paymentMethod":"COD","items":[],..}
        In order to get the paymentMethod, we need to pass it here, because it calls
        parent mapping first(if mapping method is not override or inherit)
        name starts with aa because to call it first. #T-02492
        """
        payment_method = record.get("paymentMethod")
        if payment_method:
            self.options.update(scayle_payment_method=payment_method)
        return {}

    @mapping
    def eshop_cod(self, record):
        """Mapped the eshop_cod"""
        eshop_cod = self.backend_record.is_payment_method_cod(
            record.get("paymentMethod", "")
        )
        return {"eshop_cod": eshop_cod}

    @mapping
    def eshop_payment_method(self, record):
        """Mapped the eshop_payment_method"""
        if not record.get("paymentMethod", ""):
            return {}
        return {"eshop_payment_method": record.get("paymentMethod")}

    @mapping
    def fielmann_order_number(self, record):
        """Mapped fielmann_order_number."""
        order_reference_key = record.get("orderReferenceKey")
        if not order_reference_key:
            raise MappingError(
                _("The order reference key is missing for order %(order_id)s")
                % {"order_id": record.get("orderId")}
            )

        name = f"{order_reference_key}"
        if self.backend_record.sale_prefix:
            name = f"{self.backend_record.sale_prefix}{name}"
        return {"fielmann_order_number": name}

    def get_odoo_currency(self, currency_code):
        """New Method: Added method to return mapping of currency. # T-02556"""
        if not currency_code:
            return {}
        currency = self.env["res.currency"].search([("name", "=", currency_code)])
        if not currency:
            raise MappingError(
                _("No currency was found in Odoo with currencyCode %(currency_code)s.")
                % {"currency_code": currency_code}
            )

        return {"scayle_currency_id": currency.id}

    @mapping
    def eshop_currency_id(self, record):
        """Mapped eshop_currency_id."""
        items = record.get("items", [])
        currency_code_list = [item.get("currencyCode", "") for item in items]
        if not currency_code_list or len(set(currency_code_list)) > 1:
            raise MappingError(
                _(
                    "Different currencyCode found in Items or none found for "
                    "orderId %(order_id)s."
                )
                % {"order_id": record.get("orderId")}
            )

        currency_dict = self.get_odoo_currency(currency_code_list[0])
        return {"eshop_currency_id": currency_dict.get("scayle_currency_id")}

    @mapping
    def shop_id(self, record):
        """Mapped the shop id."""
        shop_id = record.get("shopId")
        return {"shop_id": shop_id}

    @mapping
    def country_code(self, record):
        """Mapped the country code"""
        country_code = record.get("countryCode")
        return {"country_code": country_code}

    @mapping
    def shop_key(self, record):
        """Mapped the shop key"""
        shop_key = record.get("shopKey")
        return {"shop_key": shop_key}

    @mapping
    def customer_id(self, record):
        """Mapped the partner"""
        backend = self.backend_record
        partner = backend.scayle_shop_id.partner_id
        if not partner:
            raise MappingError(
                _(
                    "Please set the customer in the Scayle Shop %(scayle_shop)s,"
                    " as configured in the Scayle backend."
                )
                % {"scayle_shop": backend.scayle_shop_id.name}
            )

        return {"partner_id": partner.id}

    @mapping
    def eshop_price_with_tax(self, record):
        """#T-02515 Mapped price with tax"""
        cost = record.get("cost", {})
        eshop_price_with_tax = self.model.order_line.convert_eshop_price_to_odoo(
            cost.get("withTax", 0)
        )
        if not eshop_price_with_tax:
            return {}
        return {"eshop_price_with_tax": eshop_price_with_tax}

    @mapping
    def eshop_price_without_tax(self, record):
        """#T-02515 Mapped price without tax"""
        cost = record.get("cost", {})
        eshop_price_without_tax = self.model.order_line.convert_eshop_price_to_odoo(
            cost.get("withoutTax", 0)
        )
        if not eshop_price_without_tax:
            return {}
        return {"eshop_price_without_tax": eshop_price_without_tax}

    @mapping
    def eshop_tax_amount(self, record):
        """#T-02515 Mapped tax amount"""
        cost_dict = record.get("cost", {})
        payload_eshop_tax_amount = (
            cost_dict.get("tax", {}).get("vat", {}).get("amount", 0)
        )
        eshop_tax_amount = self.model.order_line.convert_eshop_price_to_odoo(
            payload_eshop_tax_amount
        )
        if not eshop_tax_amount:
            return {}
        return {"eshop_tax_amount": eshop_tax_amount}

    @mapping
    def partner_invoice(self, record):
        """#T-02946 Map partner_invoice_id depending on order_type
        and Scayle shop configuration."""
        backend = self.backend_record
        scayle_shop = backend.scayle_shop_id
        order_type = record.get("customData", {}).get("kls.ordertype")
        if order_type:
            self.options.update(order_type=order_type)
        if order_type and order_type.lower() == "za" and scayle_shop.za_enable:
            if scayle_shop.za_branch_partner_id:
                return {"partner_invoice_id": scayle_shop.za_branch_partner_id.id}
            partner_revenue = self._get_partner_revenue(record)
            return {"partner_invoice_id": partner_revenue.id}
        return {"partner_invoice_id": scayle_shop.partner_id.id}

    @mapping
    def eshop_shipping_tax_amount(self, record):
        """#T-02515 Mapped shipping tax amount"""
        applied_fees = self.backend_record.get_shipping_cost(record) or {}
        if "tax_amount" not in applied_fees:
            return {}
        eshop_shipping_tax_amount = self.model.order_line.convert_eshop_price_to_odoo(
            applied_fees["tax_amount"]
        )
        if not eshop_shipping_tax_amount:
            return {}
        return {"eshop_shipping_tax_amount": eshop_shipping_tax_amount}

    @mapping
    def eshop_shipping_with_tax_price(self, record):
        """#T-02515 Mapped shipping price with tax"""
        applied_fees = self.backend_record.get_shipping_cost(record) or {}
        if "withTax" not in applied_fees:
            return {}
        eshop_shipping_with_tax_price = (
            self.model.order_line.convert_eshop_price_to_odoo(applied_fees["withTax"])
        )
        if not eshop_shipping_with_tax_price:
            return {}
        return {"eshop_shipping_with_tax_price": eshop_shipping_with_tax_price}

    @mapping
    def eshop_shipping_without_tax_price(self, record):
        """#T-02515 Mapped shipping price without tax"""
        applied_fees = self.backend_record.get_shipping_cost(record) or {}
        if "withoutTax" not in applied_fees:
            return {}
        eshop_shipping_without_tax_price = (
            self.model.order_line.convert_eshop_price_to_odoo(
                applied_fees["withoutTax"]
            )
        )
        if not eshop_shipping_without_tax_price:
            return {}
        return {"eshop_shipping_without_tax_price": eshop_shipping_without_tax_price}

    @mapping
    def eshop_shipping_tax_rate(self, record):
        """#T-02515 Mapped shipping tax amount"""
        applied_fees = self.backend_record.get_shipping_cost(record) or {}
        if "tax_rate" not in applied_fees:
            return {}
        eshop_shipping_tax_rate = applied_fees["tax_rate"]
        if not eshop_shipping_tax_rate:
            return {}
        return {"eshop_shipping_tax_rate": eshop_shipping_tax_rate}

    def finalize(self, map_record, values):
        """Method to add the value for partner, partner invoice and partner shipping"""
        values.update(
            {
                "partner_id": self.options.partner_id,
                "partner_shipping_id": self.options.partner_shipping_id,
                "partner_billing_id": self.options.partner_billing_id,
                "eshop_collection_point": self.options.eshop_collection_point,
            }
        )
        # T-02506 Order Tags
        # T-02946 Add order_type
        order_tag_ids = self.env["sale.order"]._get_order_tags(
            eshop_collection_point=self.options.eshop_collection_point,
            products=self.options.products,
            backend=self.backend_record,
            payment_method=self.options.get("scayle_payment_method", ""),
            order_type=self.options.get("order_type", ""),
        )
        values.update({"tag_ids": [(6, 0, order_tag_ids)]})
        return super().finalize(map_record, values)

    @mapping
    def external_id(self, record):
        """Mapped the external id"""
        return {"external_id": record.get("orderId")}

    @mapping
    def user_id(self, record):
        """T-02076 set OdooBot as default sales person"""
        return {"user_id": SUPERUSER_ID}

    @mapping
    def pricelist_id(self, record):
        """Mapped the pricelist and check validation of pricelist from backend"""
        pricelist_id = self.backend_record._check_validation_pricelist(record)
        return {"pricelist_id": pricelist_id.id}

    @mapping
    def date_order(self, record):
        """Mapped the date order"""
        if not record.get("confirmedAt"):
            return {}
        date_order = date_parser(record.get("confirmedAt"))
        return {
            "date_order": date_order,
            "scayle_date_order": date_order,
        }

    @mapping
    def scayle_order_status(self, record):
        """Mapped the scayle order status"""
        if not record:
            return {}
        order_status = record.get("status")
        return {"scayle_order_status": order_status}

    def get_shipment_option(self, record):
        """
        New Method: Added method to return shipment option based on conditions.
        # T-02492
        """
        if self.options.eshop_collection_point:
            shipment_option = "collection_point_delivery"
        elif self.backend_record.is_payment_method_cod(record.get("paymentMethod", "")):
            shipment_option = "home_cod"
        else:
            shipment_option = "home_delivery"
        return shipment_option

    def get_shipment_option_dict(self):
        """
        New Method: Added method to return dict of shipment options to show in
        messages. # T-02492
        """
        return {
            "collection_point_delivery": "Collection Point Delivery",
            "home_delivery": "Home Delivery",
            "home_cod": "Home COD",
        }

    def get_scayle_delivery_carrier(self, record):
        """#T-02492 New Method: Generic method to return the carrier from payload."""
        carrier_key = record.get("carrier", {}).get("key", "").strip()
        # Get shipment options based on some conditions.
        shipment_option = self.get_shipment_option(record)
        domain = [
            ("eshop_carrier_code", "=ilike", carrier_key),
            ("shipment_options", "=", shipment_option),
        ]
        carrier = False

        # T-02982: Find Urbify carrier
        carrier = self._get_urbify_express_carrier(record, domain, carrier_key)

        if not carrier:
            non_urbify_domain = [("urbify_enabled", "=", False)]
            domain = expression.AND([non_urbify_domain, domain])
            carrier = self.env["delivery.carrier"].search(domain, limit=1)

        if carrier:
            return carrier
        # Get shipment options dict to show in error message.
        shipment_option_dict = self.get_shipment_option_dict()
        error_msg = _(
            "Please configure carrier code as '%(carrier_key)s' and shipment options "
            "as '%(shipment_option)s' in shipping methods."
        ) % {
            "carrier_key": carrier_key,
            "shipment_option": shipment_option_dict[shipment_option],
        }

        raise MappingError(error_msg)

    def _get_urbify_express_carrier(self, record, domain, carrier_key):
        """Handle Urbify/DHL fallback logic for EXPRESS in DE/AT. #T-02923"""
        shipping_address = record.get("addresses", {}).get("shipping", {})
        country = shipping_address.get("countryCode", "")
        shipping_zip = shipping_address.get("zipCode", "")

        if country not in ["DE", "AT"]:
            return False

        # T-02982: Determine allowed ZIP types based on the carrier key
        allowed_zip_types = (
            ["express", "both"]
            if carrier_key.lower() == "express"
            else ["non_express", "both"]
        )

        urbify_zip = self.env["delivery.carrier.urbify.zip"].search(
            [
                ("zip_code", "=", shipping_zip),
                ("carrier_type", "in", allowed_zip_types),
            ],
            limit=1,
        )

        if not urbify_zip:
            return False
        urbify_domain = [
            ("urbify_enabled", "=", True),
        ]
        updated_domain = expression.AND([urbify_domain, domain])
        delivery_carriers = self.env["delivery.carrier"].search(updated_domain)

        # T-02954: Filter by country in many2many
        delivery_carrier = delivery_carriers.filtered(
            lambda carrier: country in carrier.country_ids.mapped("code")
        )
        if len(delivery_carrier) > 1:
            raise ValidationError(
                _(
                    "Multiple Urbify delivery carriers found for country %s. "
                    "Please ensure only one is configured."
                )
                % country
            )
        return delivery_carrier or False

    def _get_partner_revenue(self, record):
        """
        T-02946:New Method: Added method to fetch revenue partner based on branchNumber.
        """
        order_type = record.get("customData", {}).get("kls.ordertype")
        # T-02953:Added condition if order_type is za or oa then revenue will
        # be set from kls.profitCenter
        if order_type and order_type.lower() in ("za", "oa"):
            revenue_store = record.get("customData", {}).get("kls.profitCenter")
        else:
            revenue_store = record.get("branchNumber") or record.get(
                "customData", {}
            ).get("branchNumber")
        if not revenue_store:
            raise MappingError(
                _("Missing branchNumber for order %s")
                % (record.get("orderReferenceKey"))
            )
        # Combine the main partner and its child partners
        partner_revenue = self.env["res.partner"].search(
            [("branch_code", "=", revenue_store)], limit=1
        )
        if not partner_revenue:
            raise MappingError(
                _("Revenue Partner with branch code %(code)s not found")
                % {"code": revenue_store}
            )

        return partner_revenue

    @mapping
    def carrier_id(self, record):
        """Mapped the carrier id"""
        # Added method which was removed as it is used in COD.
        carrier = self.get_scayle_delivery_carrier(record)
        return {"carrier_id": carrier.id}

    def get_sale_order_partner(self):
        """New Method: Return sale order's partner. # T-02652"""
        sale_order_partner = self.backend_record.scayle_shop_id.partner_id.with_company(
            self.backend_record.company_id
        )
        return sale_order_partner

    def _check_warehouse_reference_key(self, items):
        """#T-02313 Mapping Error if warehouse reference key is not present"""
        warehouses = (
            self.env["stock.warehouse"]
            .sudo()
            .search(
                [
                    ("warehouse_reference_key", "!=", False),
                ]
            )
        )
        warehouse_reference_keys = warehouses.mapped("warehouse_reference_key")
        for item in items:
            warehouse_ref_key = item.get("warehouseReferenceKey")
            if not warehouse_ref_key:
                raise MappingError(
                    _(
                        "Missing the value of warehouseReferenceKey "
                        "'%(warehouse_ref_key)s' for item '%(order_item_id)s' from "
                        "payload or missing key in item. Please check."
                    )
                    % {
                        "warehouse_ref_key": warehouse_ref_key,
                        "order_item_id": item.get("orderItemId"),
                    }
                )

            if warehouse_ref_key not in warehouse_reference_keys:
                raise MappingError(
                    _("Warehouse Reference Key %(warehouse_ref_key)s is missing!")
                    % {"warehouse_ref_key": warehouse_ref_key}
                )

        return warehouses

    def get_rxlenstype(self, item):
        consider_none = ["none", "ohne"]
        return any(
            attribute.get("name") == "rxLensType"
            and attribute.get("value") not in consider_none
            for item in item.get("subItems", [])
            for attribute in item.get("attributes", [])
        )

    def prepare_scayle_bind_vals(self, item):
        """#T-02338 Prepare the scayle bind values."""
        subitem_keys = ["id", "name", "price", "attributes"]
        subitems = [
            {key: subitem[key] for key in subitem_keys if key in subitem}
            for subitem in item.get("subItems", [])
        ]
        values = {
            "external_id": item.get("orderItemId"),
            "backend_id": self.backend_record.id,
            "scayle_quantity": item.get("quantity", 1),
            "scayle_product_name": item.get("name", ""),
            "frame_product_price": item.get("price", 0),
            "with_rxlenstype": self.get_rxlenstype(item),
            "scayle_sub_item_info": {"subItems": subitems},
            "warehouse_reference_key": item.get("warehouseReferenceKey"),
            **self.get_odoo_currency(item.get("currencyCode")),
            **self.env["scayle.sale.order.line"].get_price_tax_mapping(item=item),
        }
        return values

    def get_unique_identifier(self, item):
        """#T-02791 Method Inherit: select unique key for merging order lines."""
        identifier = item.get("merchantProductVariantReferenceKey")
        # The main idea behind to create this, is because, we are merging the lines
        # if products have same SKU, but in the case of prescription product we don't
        # have to merge it because for each prescription line we have to create
        # seperate line of SOL in Sales Order. Hence we need some unique key for
        # prescription products to avoid merging.
        if self.has_subitems(item) and self.backend_record.company_id.allow_mrp_flow:
            identifier = str(item.get("orderItemId"))
        return identifier

    def has_subitems(self, item):
        """#T-02791 Generic Method: Returns boolean is item has subitems"""
        return "subItems" in item and bool(item.get("subItems", False))

    def get_default_warehouse(self, product):
        """
        #T-02849 Retrieves the unified warehouse
        """
        orderpoints = product.orderpoint_ids.filtered(
            lambda orderpoint: orderpoint.warehouse_id
        )
        # T-02859 get warehouse from orderpoints created for product
        if orderpoints:
            return orderpoints.sorted("create_date")[0].warehouse_id
        company = self.get_company()
        return company.eshop_unified_warehouse_id

    def get_warehouse(self, item):
        """
        #T-02849 Retrieves the warehouse that has available stock for a specific
        product item.
        """
        # T-03043: Get warehouses ordered by priority (lowest first)
        warehouses = (
            self.env["stock.warehouse"]
            .sudo()
            .search([], order="sale_order_priority ASC")
        )
        product = self.env["product.product"].search(
            [("default_code", "=", item.get("merchantProductVariantReferenceKey"))],
            limit=1,
        )
        warehouse = False
        for wh in warehouses:
            stock_location_id = wh.lot_stock_id.id
            product = product.with_context(location=stock_location_id)
            # T-03043 Get HAM warehouse for just frame products
            if product.categ_id.frame_category and not self._is_external_warehouse_item(
                item=None, warehouse=wh
            ):
                warehouse = wh
                break
            sellable_qty = max(product.free_qty, 0.0)
            if not sellable_qty:
                continue
            warehouse = wh
            break
        if not warehouse:
            warehouse = self.get_default_warehouse(product)
        return warehouse

    def _get_warehouse_by_priority(self, domain=None):
        """#T-03043: Get warehouse ordered by sale_order_priority ASC, limit 1."""
        domain = domain or []
        return (
            self.env["stock.warehouse"]
            .sudo()
            .search(domain, order="sale_order_priority ASC", limit=1)
        )

    def _is_external_warehouse_item(self, item=None, warehouse=None):
        """
        #T-03043: Base Method to set True if item belongs to external warehouse.
        Took warehouse as param, if we have have warehouse then no need to call method.
        """
        if not item and not warehouse:
            return False
        if item and not warehouse:
            warehouse = self.get_warehouse(item)
        if warehouse and not warehouse.is_internal_warehouse:
            return True
        return False

    def merge_order_lines(self, items):
        """
        Merge the order line while importing the items from scayle in odoo
        For Example :

        From scayle -
        -------------------
        Product A - qty - 1
        Product A - qty - 1
        Product A - qty - 1
        Product B - qty - 1
        Product B - qty - 1

        To odoo -
        -------------------
        Product A - qty - 3
        Product B - qty - 2

        Return : Dictionary with group product per line.

        """
        merge_items = {}
        sequence = 1
        for item in items:
            # T-02849 if unified warehouse at company level then get the warehouse
            # else follow old flow.
            company = self.get_company()
            if company.eshop_unified_warehouse_id:
                warehouse = self.get_warehouse(item)
            else:
                warehouses = self._check_warehouse_reference_key(items)
                warehouse_ref_key = item.get("warehouseReferenceKey")
                warehouse = warehouses.filtered(
                    lambda w,
                    warehouse_ref_key=warehouse_ref_key: w.warehouse_reference_key
                    == warehouse_ref_key
                )
            # Reference product will change in the extension module(zeiss scayle)
            identifier = self.get_unique_identifier(item)
            product_sku = item.get("merchantProductVariantReferenceKey")
            # Hardcoded scayle logic, do not trust the payload
            quantity = 1
            # CUST-START T-02338
            bind_dict = self.prepare_scayle_bind_vals(item)
            scayle_bind_vals = (
                0,
                0,
                bind_dict,
            )
            prescription_line = self.has_subitems(item)
            sunglasses_product = self.backend_record.sunglasses_product
            if (
                prescription_line
                and sunglasses_product
                and self.backend_record.test_mode
            ):
                # T-02845 If sunglasses are selected in the backend,
                # the backend is in test mode, and an RX product is imported,
                # the SKU will be updated with "sunglasses."
                product_sku = sunglasses_product.default_code
            route = warehouse.delivery_route_id
            # TO-DO:Remove this when we don't need the old flow.
            if (
                self.backend_record.company_id.allow_mrp_flow
                and warehouse.mrp_delivery_route_id
                and prescription_line
            ):
                route = warehouse.mrp_delivery_route_id
            # CUST-END
            if identifier not in merge_items:
                merge_items[identifier] = {
                    "scayle_bind_ids": [scayle_bind_vals],
                    "quantity": quantity,
                    "product_sku": product_sku,
                    "route_id": route.id,
                    "is_designer_line": item.get("customData", {}).get(
                        "designerOrder", False
                    ),
                    "order_item_id": item.get("orderItemId"),
                    "is_prescription_line": prescription_line,
                    "is_subscription_line": item.get("customData", {}).get(
                        "subscription", False
                    ),  # T-03030 added mapping
                }
                if prescription_line:
                    merge_items[identifier]["sequence_number"] = sequence
                    sequence += 1
            else:
                merge_items[identifier]["quantity"] += quantity
                merge_items[identifier]["scayle_bind_ids"].append(scayle_bind_vals)
            partner = self.backend_record.scayle_shop_id.partner_id.with_company(
                self.backend_record.company_id
            )
            tax_records = self.env["sale.order"].get_tax_with_fiscal_position(
                product_sku, partner, self.backend_record.company_id
            )
            if not tax_records:
                continue
            merge_items[identifier].update(
                {"tax_id": [(4, tax.id) for tax in tax_records]}
            )
        return merge_items

    def _prepare_order_line_vals(self, item, product):
        """New method: T-02515 Added new method to prepare vals for sale order line."""
        total_qty = item.get("quantity", 1)
        unit_price = product.lst_price
        prescription_line = item.get("is_prescription_line", False)
        vals = {
            "product_uom_qty": total_qty,
            "product_id": product.id,
            "scayle_bind_ids": item.get("scayle_bind_ids"),
            "price_unit": unit_price,
            "tax_id": item.get("tax_id", False),
            "route_id": item.get("route_id", False),
            "is_designer_line": item.get("is_designer_line"),
            "is_subscription_line": item.get("is_subscription_line", False),  # T-03030
            "is_prescription_line": prescription_line,
            "sequence_number": item.get("sequence_number", 0),
        }
        company = self.backend_record.company_id
        if prescription_line and company.allow_mrp_flow:
            finished_categ_id = (
                product.categ_id.finished_product_category_id
                or company.finished_product_category_id
            )
            if not finished_categ_id:
                raise MappingError(
                    _(
                        "Please configure a finished product category for the "
                        "company %(company_name)s."
                    )
                    % {"company_name": company.name}
                )

            if not finished_categ_id.route_ids:
                raise MappingError(
                    _("The category '%s' does not have any routes assigned.")
                    % finished_categ_id.name
                )
            extra_weight = self.backend_record.company_id.finished_product_extra_weight
            finished_product = self.env["sale.order.line"].create_finished_product(
                product_name=product.name,
                default_code=item.get("order_item_id"),
                category=finished_categ_id,
                weight=product.weight + extra_weight,
                pim_image_url=product.pim_image_url,
            )
            vals["frame_product_id"] = product.id
            vals["product_id"] = finished_product.id
        return vals

    # Commented code for future reference. # T-02556
    # Creation for shipping line without binding.
    # def _prepare_shipping_line_values(self, record):
    #     """#T-02492 New Method: Prepare shipping line values to add shipping line."""
    #     backend = self.backend_record
    #     delivery_carrier = self.get_scayle_delivery_carrier(record)
    #     # T-02515 START
    #     applied_fees_dict = backend.get_shipping_cost(record, should_check=True)
    #     if not applied_fees_dict:
    #         return {}
    #     line_tax = 0.0
    #     delivery_carrier_product = delivery_carrier.product_id
    #     # For shipping tax percent comes in 0.19 format so multiply with 100 to get
    #     # tax.
    #     tax_percent = float(applied_fees_dict.get("tax_rate", 0.0))
    #     line_tax = self.env["scayle.sale.order.line"].get_scayle_line_tax(
    #         tax_percent=tax_percent,
    #         backend=backend,
    #         price_include=backend.tax_included,
    #     )
    #     return {
    #         "product_id": delivery_carrier_product.id,
    #         "price_unit": delivery_carrier_product.lst_price,
    #         "is_delivery": True,
    #         "tax_id": line_tax if line_tax else False,  # T-02515
    #     }

    @mapping
    def order_line(self, record):
        """Mapped the order line per group from the scayle."""
        items = record.get("items")
        merge_items = self.merge_order_lines(items)
        order_line = []
        products_dict = {}
        # T-02999 prepare product dictionary for each item as previously using product
        # as identifier not able to add tags in case same product received in payload
        # as just frame as well as RX.
        for item_count, item in enumerate(merge_items.values(), start=1):
            product = self.env["sale.order"].get_product(item.get("product_sku"))
            # Added param product and also used to update in options.
            vals = self._prepare_order_line_vals(item=item, product=product)
            products_dict[item_count] = {
                "is_prescription_line": vals.get("is_prescription_line", False),
                "is_designer_line": vals.get("is_designer_line", False),
                "is_subscription_line": item.get(
                    "is_subscription_line", False
                ),  # T-03030
                # Pass product record to use it getting tags for order
                "product": product,
            }
            order_line.append((0, 0, vals))
        self.options.update({"products": products_dict})
        # Commented code for future reference. # T-02556
        # Creation for shipping line without binding.
        # shipping_line_values = self._prepare_shipping_line_values(record)
        # if shipping_line_values:
        #     order_line.append((0, 0, shipping_line_values))
        return {"order_line": order_line}

    def get_company(self):
        """Helper method to get the company from scayle backend."""
        backend = self.backend_record
        company = backend.company_id
        if not company:
            raise MappingError(
                _(
                    "The company is not set on the scayle backend '%(backend_name)s'. "
                    "Please check !!!"
                )
                % {"backend_name": backend.name}
            )

        return company

    @mapping
    def company_id(self, record):
        """Mapped the company id"""
        company = self.get_company()
        return {"company_id": company.id}

    @mapping
    def warehouse_id(self, record):
        """Mapped the warehouse id"""
        company = self.get_company()
        # T-03043: Set Warehouse based on priority.
        warehouse = self._get_warehouse_by_priority(
            domain=[("company_id", "=", company.id)]
        )
        if not warehouse:
            raise MappingError(
                _("There is no warehouse for company %(company_name)s")
                % {"company_name": company.name}
            )

        return {"warehouse_id": warehouse.id}

    @mapping
    def scayle_shop_id(self, record):
        """Mapped the scayle shop id from scayle backend."""
        scayle_shop = self.backend_record.scayle_shop_id
        if not scayle_shop:
            raise MappingError(
                _("Please Configure Scayle Shop for backend %(backend_name)s.")
                % {"backend_name": self.backend_record.name}
            )

        return {"scayle_shop_id": scayle_shop.id}

    @mapping
    def team_id(self, record):
        """Mapped the sales team id from scayle shop."""
        backend = self.backend_record
        return {"team_id": backend.scayle_shop_id.sales_team_id.id}

    @mapping
    def partner_revenue(self, record):
        """#T-02823 Add the mapping for the revenue partner from scayle"""
        # T-02946 Added method which return partner_revenue_id.
        partner_revenue = self._get_partner_revenue(record)
        return {"partner_revenue_id": partner_revenue.id}

    @mapping
    def fiscal_position_id(self, record):
        """New Method: Mapping of fiscal_position_id"""
        partner = self.get_sale_order_partner()
        fiscal_position = self.env["sale.order"].get_fiscal_position_from_partner(
            partner
        )
        if not fiscal_position:
            return {}
        return {"fiscal_position_id": fiscal_position.id}


class SaleOrderImporter(Component):
    _name = "scayle.sale.order.importer"
    _inherit = "scayle.importer"
    _apply_on = "scayle.sale.order"

    def _after_import(self, binding, **kwargs):
        order = binding.odoo_id
        # T-02935 Check if customer is in blacklist
        blacklist_data = order.check_blacklist_values()
        blacklisted = blacklist_data["blacklists"]
        if blacklisted:
            reasons = blacklist_data["reasons"]
            order.action_lock()
            # T-02935 Create reservation
            order.create_reservation()
            # T-03107 Added blacklisted filter names
            message = _("The order has been locked for manual review.")
            blacklist_names = [name for name in blacklisted.mapped("name") if name]
            message += (
                "<br/><br/>"
                + "<b>Matched Blacklist Filters:</b><ul>%s</ul>"
                % "".join(f"<li>{name}</li>" for name in blacklist_names)
            )

            blacklist_reasons = []

            # T-02935 Customer blacklist reason
            if reasons["customer"]:
                blacklist_reasons.append("<li>Customer is blacklisted.</li>")

            # T-03107 Product blacklist reason
            if reasons["products"]:
                product_message = "<br/><br/>".join(
                    (
                        f"<b>Frame Product (Blacklisted):</b>"
                        f"<br/>- {pd['frame_product']}"
                        f"<br/><b>Related Finished Products:</b>"
                        f"<br/>{finished_products}"
                    )
                    for pd in reasons["products"]
                    for finished_products in [
                        "<br/>".join(f"- {fb}" for fb in pd["finished_products"])
                    ]
                )
                blacklist_reasons.append(
                    "<li>Blacklisted Products:<br/>%s</li>" % product_message
                )

            if blacklist_reasons:
                message += "<b>Blacklist Reasons:</b><ol>%s</ol>" % "".join(
                    blacklist_reasons
                )

            # T-02935 Post message
            order.message_post(body=Markup(message))

            try:
                # T-03107 send mail to notify user for blacklisted values
                if reasons["customer"] or reasons["products"]:
                    template = self.env.ref(
                        "connector_scayle.email_template_blacklist_customer",
                        raise_if_not_found=False,
                    )
                    if template:
                        template.with_context(
                            blacklist_customer=reasons["customer"],
                            blacklist_products=reasons["products"],
                            blacklist_filters=blacklist_names,
                        ).send_mail(order.id, force_send=False)
            except Exception as ex:
                _logger.error(
                    "Failed to send blacklist notification email for order %s: %s",
                    order.id,
                    ex,
                )
        # T-03053: Consolidation of Mix Orders
        # order._check_and_apply_mltp_route()
        if self.backend_record.auto_confirm_order and not blacklisted:
            order.with_company(order.company_id).sudo().action_confirm()
        return super()._after_import(binding)

    def _must_skip(self):
        """Skipped Record which are already imported."""
        if self.binder.to_internal(self.external_id):
            return _("Already imported")
        return super()._must_skip()

    def update_collection_point_to_ship_address(self, scayle_record, collection_point):
        """
        #T-02506 Prepare the collection point data based on carrier
        (Currently supported for carrier type 'DHL' and 'INPOST_PL').
        """
        carrier_type = scayle_record.get("carrier", {}).get("key", "").strip()
        shipping_method = (
            self.env["delivery.carrier"]
            .sudo()
            .search(
                [
                    ("eshop_carrier_code", "=ilike", carrier_type.upper()),
                    ("shipment_options", "=", "collection_point_delivery"),
                ],
                limit=1,
            )
        )
        if not shipping_method:
            raise MappingError(
                _(
                    "Please configure shipping method for carrier %(carrier_type)s with"
                    " shipment options %(shipment_options)s."
                )
                % {
                    "carrier_type": carrier_type,
                    "shipment_options": "collection_point_delivery",
                }
            )

        collection_point_data = {}
        cp_customer_key = shipping_method.customer_key
        cp_address = shipping_method.address_key

        if cp_customer_key in collection_point and collection_point.get(
            cp_customer_key
        ):
            collection_point_data.update(
                {"cp_customer_number": collection_point.get(cp_customer_key)}
            )
        if cp_address in collection_point and collection_point.get(cp_address):
            collection_point_data.update(
                {
                    "cp_address": collection_point.get(cp_address),
                }
            )
        return collection_point_data

    def create_address(self, address_record):
        """Create the address with mapped fields # T-02076"""
        address_bind = self.env["scayle.address"].create(address_record)
        return address_bind.odoo_id

    def search_address(self, address, customer):
        """
        #T-02862 New Method: Common logic to generate hash and search the scayle address
        """
        address_hash = self.env["res.partner"]._generate_address_hash(address)
        address = None
        address = (
            self.env["scayle.address"]
            .with_context(active_test=False)
            .search(
                [
                    ("address_hash_code", "=", address_hash),
                    ("scayle_parent_id", "=", customer.get("referenceKey")),
                    ("backend_id", "=", self.backend_record.id),
                ],
                limit=1,
            )
        )
        return address_hash, address

    def create_get_address(self, address_dict, customer):
        """#T-02862 New Method: To retrive existing or create new address"""
        address_hash, address = self.search_address(address_dict, customer)
        partner_id = address.odoo_id
        if not partner_id.active:
            partner_id.write({"active": True})
        if not address:
            address_dict.update({"address_hash_code": address_hash})
            address = self.create_address(address_dict)
        else:
            address = partner_id
        return address

    def prepare_and_process_address(
        self, record, addresses_defaults, customer, address_type
    ):
        """#T-02862 New Method: To validate and map address data"""
        addr_mapper = self.component(usage="import.mapper", model_name="scayle.address")
        address_dict = record.get("addresses").get(address_type) or {}
        if not address_dict:
            raise MappingError(
                _("%s Address is not available") % address_type.capitalize()
            )
        # T-02506 - Collection Point Shipping Address START
        collection_point = address_dict.get("collectionPoint", {})
        if (
            isinstance(collection_point, dict)
            and collection_point
            and address_type == "shipping"
        ):
            self.eshop_collection_point = True
            collection_point_data = self.update_collection_point_to_ship_address(
                scayle_record=record, collection_point=collection_point
            )
            address_dict.update(collection_point_data)
        # T-02816 We map the record values so it will be usable if new scayle address
        # needs to be created (address_dict in mapper returns the object)
        # used map_record.values to convert in dictionary
        address_dict = addr_mapper.map_record(address_dict).values()
        address_dict.update(addresses_defaults)
        # # T-02818: Unarchived partner if partner is archived at time of import
        address = self.create_get_address(address_dict, customer)
        return address

    def _import_addresses(self):
        record = self.eshop_record
        customer = record.get("customer", {})
        # Initialize Value for collection point
        self.eshop_collection_point = False
        if not customer:
            raise InvalidDataError(
                _("Order %(order_id)s has no customer.")
                % {"order_id": record.get("orderId")}
            )

        # Update address
        customer_address = record.get("addresses") or {}
        customer_address = customer_address.get("shipping") or {}
        customer["addresses"] = customer_address
        addresses_defaults = {
            "scayle_parent_id": customer.get("referenceKey"),
            "backend_id": self.backend_record.id,
            "active": True,
            "email": customer.get("email"),
        }
        shipping = self.prepare_and_process_address(
            record, addresses_defaults, customer, address_type="shipping"
        )
        # Scayle shop customer
        scayle_shop_partner = self.backend_record.scayle_shop_id.partner_id
        self.partner_id = scayle_shop_partner.id
        self.partner_shipping_id = shipping.id
        self.partner_billing_id = self.set_billing_partner(record, addresses_defaults)

    def set_billing_partner(self, record, addresses_defaults):
        """
        #T-02862 New Method: To prepare billing address for customer and
        link with shipping address
        """
        customer = record.get("customer", {})
        billing = self.prepare_and_process_address(
            record, addresses_defaults, customer, address_type="billing"
        )
        return billing.id

    def _check_special_fields(self):
        assert self.partner_id, (
            "self.partner_id should have been defined "
            "in SaleOrderImporter._import_addresses"
        )
        assert self.partner_shipping_id, (
            "self.partner_shipping_id should have been defined "
            "in SaleOrderImporter._import_addresses"
        )

    def _create_data(self, map_record, **kwargs):
        self._check_special_fields()
        return super()._create_data(
            map_record,
            partner_id=self.partner_id,
            partner_shipping_id=self.partner_shipping_id,
            partner_billing_id=self.partner_billing_id,
            eshop_collection_point=self.eshop_collection_point,
            **kwargs,
        )

    def _update_data(self, map_record, **kwargs):
        self._check_special_fields()
        return super()._update_data(
            map_record,
            partner_id=self.partner_id,
            partner_shipping_id=self.partner_shipping_id,
            partner_billing_id=self.partner_billing_id,
            eshop_collection_point=self.eshop_collection_point,
            **kwargs,
        )

    def _import_dependencies(self, always):
        res = super()._import_dependencies(always)
        self._import_addresses()
        return res
