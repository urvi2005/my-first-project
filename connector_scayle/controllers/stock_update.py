import json
import logging
import uuid

from werkzeug.exceptions import Forbidden, NotFound

from odoo import _, fields, http
from odoo.http import request
from odoo.osv import expression

from odoo.addons.connector_settings.components.misc import get_access_token

_logger = logging.getLogger(__name__)


class StockEndPointController(http.Controller):
    # Define search models (should be changed by pim modules to the binding model)
    _product_model = "product.product"

    def search_and_get_stock_update_dates(
        self,
        warehouse,
        sku_list,
        from_date=None,
        to_date=None,
        limit=None,
        offset=None,
    ):
        """
        Search the stock update lines for product  based on from_date to to_date
        with limit and offset
        """
        domain = [("warehouse_id", "=", warehouse.id)]
        sws_date_domain = []
        inv_date_domain = []
        if from_date:
            from_date = fields.Datetime.from_string(from_date)
            inv_date_domain = expression.AND(
                [
                    inv_date_domain,
                    [("inventory_update_date", ">=", from_date)],
                ]
            )
            sws_date_domain = expression.AND(
                [sws_date_domain, [("sws_update_date", ">=", from_date)]]
            )
        if to_date:
            to_date = fields.Datetime.from_string(to_date)
            inv_date_domain = expression.AND(
                [inv_date_domain, [("inventory_update_date", "<=", to_date)]]
            )
            sws_date_domain = expression.AND(
                [sws_date_domain, [("sws_update_date", "<=", to_date)]]
            )
        if inv_date_domain and sws_date_domain:
            date_domain = expression.OR([inv_date_domain, sws_date_domain])
            domain = expression.AND([domain, date_domain])

        # T-02331: search stock_update_dates based on from_date and to_date
        stock_update_date_obj = request.env["stock.update.date"].sudo()
        if sku_list:
            domain = expression.AND(
                [domain, [("product_id.default_code", "in", sku_list)]]
            )
        else:
            domain = expression.AND(
                [domain, [("product_id.default_code", "!=", False)]]
            )
        # T-02457 It will get the product which will have product category level field
        # eshop_skip_inventory_update set False.
        domain = expression.AND(
            [domain, [("product_id.categ_id.eshop_skip_inventory_update", "=", False)]]
        )
        stock_update_date_lines = stock_update_date_obj.search(
            domain, offset=offset, limit=limit
        )
        return stock_update_date_lines

    def get_unified_warehouse_reference_key(self, unified_warehouse):
        """#T-02849 New Method: get unified warehouse reference key"""
        warehouse_reference_keys = []
        if unified_warehouse.warehouse_reference_key:
            warehouse_reference_keys.append(unified_warehouse.warehouse_reference_key)
        # T-02849 If not warehouse reference key then send validation
        if not warehouse_reference_keys:
            _logger.error("Unified warehouse not set at company level.")
            raise NotFound(_("Unified warehouse not set at company level."))
        return warehouse_reference_keys

    @http.route(
        [
            "/api/scayle/v1/get-stock-update",
            "/api/scayle/v1/get-stock-update/<access_token>",
        ],
        auth="public",
        type="json",
        methods=["GET"],
    )
    def get_stock_update(
        self,
        warehouse_reference_keys=None,
        product_sku_lst=None,
        from_date=None,
        to_date=None,
        access_token=None,
        limit=None,
        offset=None,
    ):
        """Returns the stock of the products on for every warehouse to scayle."""
        access_token = get_access_token(
            access_token=access_token, header=request.httprequest.headers
        )
        if not access_token:
            _logger.error("Invalid access token !")
            raise Forbidden()
        backend = (
            request.env["scayle.backend"]
            .sudo()
            .search(
                [
                    "|",
                    "&",
                    ("test_mode", "!=", True),
                    ("odoo_scayle_token", "=", f"{access_token}"),
                    "&",
                    ("test_odoo_scayle_token", "=", f"{access_token}"),
                    ("test_mode", "=", True),
                ],
                limit=1,
            )
        )
        if not backend:
            _logger.error("Invalid access token !")
            raise Forbidden()

        if not backend.stock_endpoint:
            _logger.info("Stock update endpoint is disabled")
            raise Forbidden()

        if product_sku_lst is None:
            product_sku_lst = []

        request_uuid = str(uuid.uuid4())
        _logger.info(
            f"Stock update request parameters: uuid:{request_uuid}, "
            f"from_date:{from_date}, to_date: {to_date},"
            f"warehouses: {warehouse_reference_keys}, limit: {limit}"
            f", offset: {offset}, SKUs: {product_sku_lst} "
        )
        # T-02849 Check if a unified warehouse is configured for the company's eShop.
        # If it exists, follow the unified warehouse flow to get updated product
        # inventory.
        unified_warehouse = backend.company_id.eshop_unified_warehouse_id

        # T-02849 If not received warehouse reference key then take unified as default
        if not warehouse_reference_keys:
            warehouse_reference_keys = self.get_unified_warehouse_reference_key(
                unified_warehouse
            )

        if unified_warehouse:
            product_inventory_dict = self.get_updated_stock_for_unified_warehouse(
                request_uuid,
                backend,
                warehouse_reference_keys,
                product_sku_lst,
                from_date,
                to_date,
                access_token,
                limit,
                offset,
            )
            return product_inventory_dict

        # T-02337: change warehouse_reference_keys to platlling
        if "odoo" in warehouse_reference_keys:
            warehouse_reference_keys = list(
                map(
                    (lambda x: x.replace("odoo", "plattling")), warehouse_reference_keys
                )
            )
        # Determine the warehouse based on reference key.
        warehouses = (
            request.env["stock.warehouse"]
            .sudo()
            .search(
                [
                    # T-02556 Updating the condition to filter warehouses based on
                    # their associated company_id, ensuring that only warehouses
                    # with company_id and warehouse_reference_key are considered for
                    # further processing.
                    ("warehouse_reference_key", "in", warehouse_reference_keys),
                ]
            )
        )
        if not warehouses:
            _logger.error(
                "The given warehouse reference key does not belong to"
                " any warehouse in odoo."
            )
            raise NotFound(
                _(
                    "The given warehouse reference keys does not belong"
                    " to any warehouse in odoo."
                )
            )

        product_inventory_dict = {"id": request_uuid}
        warehouse_message_list = []
        # If warehoues are available, then only we have to search for the records.
        # Searching all the records from eshop.stock.ratio, instead inside of
        # for loop to make sure that we only have to read the data only once.

        # If the scayle_skip_inventory_update is true for category, we don't
        # need those categories, as those products and stock update dates are never
        # received from the domain which has scayle_skip_inventory_update=True
        # in category
        categoryObj = request.env["product.category"].sudo()
        # T-02849 Moved the logic of scayle_ratio_dict to method get_scayle_ratio_dict
        # T-02863 Get scayle ratio and brand_ratio dict.
        scayle_ratio_dict, brand_scayle_ratio_dict = self.get_scayle_ratio_dict()
        for warehouse in warehouses:
            stock_inventory_list = []
            # Search for the products from_date to to_date.
            stock_update_dates = self.search_and_get_stock_update_dates(
                warehouse=warehouse,
                sku_list=product_sku_lst,
                from_date=from_date,
                to_date=to_date,
                limit=limit,
                offset=offset,
            )
            for stock_update_date in stock_update_dates:
                # T-02331: the value inventory_update_date and sws_update_date is
                # getting from the stock_update_date_ids
                product = stock_update_date.product_id.with_context(
                    warehouse=warehouse.id
                )
                inventory_update_date = (
                    stock_update_date.inventory_update_date.strftime(
                        "%m/%d/%Y, %H:%M:%S"
                    )
                    if stock_update_date.inventory_update_date
                    else ""
                )
                sws_update_date = (
                    stock_update_date.sws_update_date.strftime("%m/%d/%Y, %H:%M:%S")
                    if stock_update_date.sws_update_date
                    else ""
                )
                qty = max(product.qty_available - product.outgoing_qty, 0.0)
                # T-02863 Get Stock Ratios.
                scayle_ratio = self.get_scayle_stock_ratio(
                    product, scayle_ratio_dict, brand_scayle_ratio_dict
                )
                if not backend.backend_group_id:
                    sellable_quantity = 0
                elif not scayle_ratio:
                    sellable_quantity = qty
                else:
                    sellable_quantity = categoryObj.allocate_stock(
                        total_quantity=qty,
                        shop_percentage_values=scayle_ratio,
                        threshold_qty=product.categ_id.min_threshold_qty,
                        max_buffer=product.categ_id.security_max_buffer,
                        backend_group=backend.backend_group_id,
                    )
                stock_inventory_list.append(
                    {
                        "sellableWithoutStock": product.eshop_sws,  # T-02079
                        "quantity": sellable_quantity,  # (on hand quantity -
                        # outgoing qty) * percentage from category
                        "sellableQuantity": sellable_quantity,  # T-02583
                        "changedAt": inventory_update_date,
                        # T-02294 add new timestamp for sws
                        "sws_update_date": sws_update_date,
                        "product_sku": product.default_code,
                    }
                )
            warehouse_key = warehouse.warehouse_reference_key
            if warehouse_key not in product_inventory_dict:
                product_inventory_dict[warehouse_key] = {
                    "stock_inventory": stock_inventory_list
                }
            else:
                product_inventory_dict.get(warehouse_key).get("stock_inventory").extend(
                    stock_inventory_list
                )
            total_stock_dates = len(stock_update_dates)
            product_inventory_dict[warehouse_key].update(
                {"total_product_count": total_stock_dates}
            )
            warehouse_message_list.append(f"{warehouse_key} - {total_stock_dates}")
        _logger.info(
            ("Stock update response for {}: {}").format(
                request_uuid, " / ".join(warehouse_message_list)
            )
        )
        # T-02337: set sellableWithoutStock for the barsbuettel warehouse
        # from hotfix fielmann scayle
        if "barsbuettel" in product_inventory_dict.keys():
            stock_dict_data = product_inventory_dict.get("barsbuettel").get(
                "stock_inventory"
            )
            for data in stock_dict_data:
                data.update({"sellableWithoutStock": False})
        return json.dumps(product_inventory_dict)

    def get_scayle_stock_ratio(
        self, product, scayle_ratio_dict, brand_scayle_ratio_dict
    ):
        """# T-02863 Generic Method : Return Scayle Stock Ratio."""
        # T-02863 scayle_ratio from eshop_stock_ratio.
        scayle_ratio = scayle_ratio_dict.get(product.categ_id.id, [])
        # T-02863 Check branded product
        brand_product = product.product_brand_id
        if not brand_product:
            return scayle_ratio
        # T-02863 get brand ratios from eshop_brand_ratios.
        brand_ratios = brand_scayle_ratio_dict.get(product.categ_id.id, {}).get(
            product.product_brand_id.id, []
        )
        return brand_ratios or scayle_ratio

    def search_and_get_stock_update_dates_for_unified_warehouse(
        self,
        sku_list,
        from_date=None,
        to_date=None,
        limit=None,
        offset=None,
    ):
        """
        #T-02849 Search the stock update lines for product based on from_date to to_date
        with limit and offset
        """
        domain = []
        sws_date_domain = []
        inv_date_domain = []
        # If from_date is provided, filter records where the dates are greater than or
        # equal to from_date
        if from_date:
            from_date = fields.Datetime.from_string(from_date)
            inv_date_domain = expression.AND(
                [
                    inv_date_domain,
                    [("inventory_update_date", ">=", from_date)],
                ]
            )
            sws_date_domain = expression.AND(
                [sws_date_domain, [("sws_update_date", ">=", from_date)]]
            )
        # If to_date is provided, filter records where the dates are less than or equal
        # to to_date
        if to_date:
            to_date = fields.Datetime.from_string(to_date)
            inv_date_domain = expression.AND(
                [inv_date_domain, [("inventory_update_date", "<=", to_date)]]
            )
            sws_date_domain = expression.AND(
                [sws_date_domain, [("sws_update_date", "<=", to_date)]]
            )
        # Combine both date domains if both are defined (either inventory or sws)
        if inv_date_domain and sws_date_domain:
            date_domain = expression.OR([inv_date_domain, sws_date_domain])
            domain = expression.AND([domain, date_domain])
        stock_update_date_obj = request.env["stock.update.date"].sudo()
        # If sku_list is provided, filter records for those specific SKU codes
        if sku_list:
            domain = expression.AND(
                [domain, [("product_id.default_code", "in", sku_list)]]
            )
        else:
            domain = expression.AND(
                [domain, [("product_id.default_code", "!=", False)]]
            )
        # Ensure the products selected are not marked to skip inventory update in e-shop
        domain = expression.AND(
            [domain, [("product_id.categ_id.eshop_skip_inventory_update", "=", False)]]
        )
        # Define the fields to read from the database: max of inventory and sws update
        # dates for each product
        fields_to_read = [
            "product_id",
            "inventory_update_date:max",
            "sws_update_date:max",
        ]
        # Perform a read_group query to get the stock update date lines.
        stock_update_date_lines = stock_update_date_obj.with_context().read_group(
            domain,
            fields_to_read,
            groupby=["product_id"],
            offset=offset,
            limit=limit,
        )
        return stock_update_date_lines

    def get_scayle_ratio_dict(self):
        """
        #T-02849 Returns a dictionary of stock ratios for categories that need inventory
        updates.
        1. A dictionary of stock ratios for categories based on `eshop_stock_ratio_ids`
        2. A dictionary of stock ratios for categories based on `eshop_brand_ratio_ids`
        """

        scayle_ratio_dict = {}
        brand_scayle_ratio_dict = {}

        # T-02863 Search for categories where inventory updates are needed and
        # stock ratios exist
        product_categories = (
            request.env["product.category"]
            .sudo()
            .search(
                [
                    ("eshop_skip_inventory_update", "=", False),
                    "|",
                    ("eshop_stock_ratio_ids", "!=", False),
                    ("eshop_brand_ratio_ids", "!=", False),
                ]
            )
        )
        for product_category in product_categories:
            # T-02863 Normal stock ratios form backend groups.
            # Update the scayle_ratio_dict with the category ID as the key and its stock
            # ratios as the value
            scayle_ratio_dict.update(
                {
                    product_category.id: [
                        {
                            "percentage": ratio.percentage,
                            "backend_group_id": ratio.backend_group_id,
                        }
                        # T-02583 Extra Condition to make sure that we get the
                        # o2m field values from high-to-low percentage vise.
                        for ratio in product_category.eshop_stock_ratio_ids.filtered(
                            lambda stock_ratio: stock_ratio.percentage
                        ).sorted("percentage", reverse=True)
                    ]
                }
            )
            # T-02863 Brand-specific stock ratios.
            product_brand_grouped = {}
            # T-02863 Iterate over all brand-specific stock ratios in the category
            for ratio in product_category.eshop_brand_ratio_ids.filtered(
                lambda a: a.percentage > 0
            ).sorted(key=lambda a: a.percentage, reverse=True):
                if not ratio.percentage or not ratio.product_brand_id:
                    continue
                # T-02863 Group ratios under their product_brand_id using setdefault
                product_brand_grouped.setdefault(ratio.product_brand_id.id, []).append(
                    {
                        "percentage": ratio.percentage,
                        "backend_group_id": ratio.backend_group_id,
                    }
                )
            # T-02863 Sort each brand's list of ratios by percentage in descending order
            brand_scayle_ratio_dict.update({product_category.id: product_brand_grouped})

        # T-02863 return both dictionaries.
        return scayle_ratio_dict, brand_scayle_ratio_dict

    def get_updated_stock_for_unified_warehouse(
        self,
        request_uuid=None,
        backend=None,
        warehouse_reference_keys=None,
        product_sku_lst=None,
        from_date=None,
        to_date=None,
        access_token=None,
        limit=None,
        offset=None,
    ):
        """
        #T-02849 Returns the stock of the products on for unified warehouse to scayle.
        """
        # Get the unified warehouse reference key for the current company
        unified_warehouse_id = backend.company_id.eshop_unified_warehouse_id
        unified_warehouse_key = unified_warehouse_id.warehouse_reference_key
        product_inventory_dict = {"id": request_uuid}
        warehouse_message_list = []
        # Get the product category object and fetch stock ratios for categories
        categoryObj = request.env["product.category"].sudo()
        # T-02863 Get scayle ratio and brand_ratio dict.
        scayle_ratio_dict, brand_scayle_ratio_dict = self.get_scayle_ratio_dict()
        stock_inventory_list = []
        # Get stock update dates for the given SKU list and date range
        stock_update_dates = (
            self.search_and_get_stock_update_dates_for_unified_warehouse(
                sku_list=product_sku_lst,
                from_date=from_date,
                to_date=to_date,
                limit=limit,
                offset=offset,
            )
        )
        # T-02849 : Compute stock quantities for stock update
        # We have adapted this approach to make the performance better,by
        # pre-fetching all the data at once, and storing it at the level of cache.
        # this will hit less sql queries internally.
        # For eg : for the 1000 records earlier it was taking around 8 seconds, but
        # now it takes Approx 1 seconds.[logic is not changed]
        product_ids = [stock["product_id"][0] for stock in stock_update_dates]
        # T-02896 get appropriate values for stock update of scayle
        stock_location_context = request.env[
            "product.product"
        ]._get_stock_update_location_context(backend.company_id.id)
        ProductProduct = (
            request.env["product.product"].sudo().with_context(**stock_location_context)
        )
        products = ProductProduct.browse(product_ids)
        products.mapped("qty_available")
        products.mapped("outgoing_qty")
        for stock_update_date in stock_update_dates:
            # Get the product ID from the stock update line and fetch product details
            product_id_value = stock_update_date.get("product_id")[0]
            product = ProductProduct.browse(product_id_value)
            # Format the inventory update and sws update dates
            inventory_update_date = (
                stock_update_date.get("inventory_update_date").strftime(
                    "%m/%d/%Y, %H:%M:%S"
                )
                if stock_update_date.get("inventory_update_date")
                else ""
            )
            sws_update_date = (
                stock_update_date.get("sws_update_date").strftime("%m/%d/%Y, %H:%M:%S")
                if stock_update_date.get("sws_update_date")
                else ""
            )
            # Get the free quantity, ensuring it's non-negative
            qty = max(product.free_qty, 0.0)
            # T-02863 Get Stock Ratios.
            scayle_ratio = self.get_scayle_stock_ratio(
                product, scayle_ratio_dict, brand_scayle_ratio_dict
            )
            # Calculate sellable quantity based on the backend and stock ratios
            if not backend.backend_group_id:
                sellable_quantity = 0
            elif not scayle_ratio:
                sellable_quantity = qty
            else:
                sellable_quantity = categoryObj.allocate_stock(
                    total_quantity=qty,
                    shop_percentage_values=scayle_ratio,
                    threshold_qty=product.categ_id.min_threshold_qty,
                    max_buffer=product.categ_id.security_max_buffer,
                    backend_group=backend.backend_group_id,
                )

            # Add the stock information for the product to the stock inventory list
            stock_inventory_list.append(
                {
                    "sellableWithoutStock": product.eshop_sws,
                    "quantity": sellable_quantity,
                    "sellableQuantity": sellable_quantity,
                    "changedAt": inventory_update_date,
                    "sws_update_date": sws_update_date,
                    "product_sku": product.default_code,
                }
            )

        # Add stock_inventory_list to the product_inventory_dict
        product_inventory_dict[unified_warehouse_key] = {
            "stock_inventory": stock_inventory_list
        }
        total_stock_dates = len(stock_update_dates)
        product_inventory_dict[unified_warehouse_key].update(
            {"total_product_count": total_stock_dates}
        )
        warehouse_message_list.append(f"{unified_warehouse_key} - {total_stock_dates}")
        _logger.info(
            ("Stock update response for {}: {}").format(
                request_uuid, " / ".join(warehouse_message_list)
            )
        )
        # If unified warehouse key is not present in warehouse_reference_keys then
        # pop that unified warehouse from the outcome of product_inventory_dict
        if unified_warehouse_key not in warehouse_reference_keys:
            product_inventory_dict.pop(unified_warehouse_key, None)
        product_inventory_dict = json.dumps(product_inventory_dict)
        if (
            backend.backend_group_id.show_stock_update_response
        ):  # log only if Boolean is true #T-02931
            _logger.info(
                "Stock Inventory Response:\n%s",
                product_inventory_dict,
            )
        return product_inventory_dict
