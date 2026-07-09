import logging
import pprint

from odoo import SUPERUSER_ID, _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.connector_settings.components.misc import get_access_token
from odoo.addons.queue_job.job import identity_exact

_logger = logging.getLogger(__name__)


class OrderCreateEndPointController(http.Controller):
    _duplicate_msg = _("The sale order is already imported.")

    def validate_address(self, address, address_type):
        """#T-02076 Validate the address of the customer."""
        msg = False
        required_fields = [
            "streetHouseNumber",
            "city",
            "countryCode",
            "zipCode",
        ]
        missing_fields = [field for field in required_fields if not address.get(field)]
        if missing_fields:
            msg = _(
                "Missing customer %(missing_fields)s in %(address_type)s address."
            ) % {
                "missing_fields": ",".join(missing_fields),
                "address_type": address_type,
            }

        return msg

    def check_multiple_warehouses(self, item_list=False):
        """
        NEW-METHOD:Added new method for checking that particular Scayle order
        has products of different warehouses with shipping cost more than one #T-02492
        """
        msg = False
        warehouse_list = [item.get("warehouseReferenceKey") for item in item_list]
        if len(set(warehouse_list)) > 1:
            msg = (
                "Scayle Order has different warehouseReferenceKey with COD order and"
                " shippingCost greater than 0!"
            )
        return msg

    def get_error_message(self, data, backend=None):
        """
        #T-02076 Return error message as per conditions: if some data from payload
        not fetched as per needed
        """
        if not data:
            _logger.warning("Received empty payload")
            msg = _("Received empty payload.")
            return msg
        external_id = data.get("orderId", False)
        if not external_id:
            _logger.warning("orderId is missing from the payload")
            msg = _("orderId is missing from the payload.")
            return msg

        if not data.get("orderReferenceKey"):
            _logger.warning("'orderReferenceKey' is missing from the payload.")
            msg = _("'orderReferenceKey' is missing from the payload")
            return msg
        msg = self.check_sale_order(data=data, external_id=external_id, backend=backend)
        if msg:
            return msg
        cost_dict = data.get("cost", {})
        if "appliedFees" in cost_dict:
            msg = backend.check_shipping_delivery_cost(cost_dict["appliedFees"])
            if msg:
                _logger.warning(msg)
                return msg
        # T-02726 Method added from connector_scayle_code
        backend_cod_method = (
            backend.cod_payment_method.strip().lower()
            if backend.cod_payment_method
            else ""
        )
        scayle_payment_method = data.get("paymentMethod").strip().lower()
        if not backend_cod_method or backend_cod_method != scayle_payment_method:
            return False
        applied_fees = backend.get_shipping_cost(data)
        # If other than deliveryCosts present then raise.
        items = data.get("items", [])
        if (
            applied_fees
            and applied_fees.get("withoutTax")
            and applied_fees.get("withoutTax") > 0
        ):
            msg = self.check_multiple_warehouses(item_list=items)
        if msg:
            _logger.warning(msg)
            return msg
        # Applied this logic for same items having different taxes. #T-02515
        tax_dict = {}
        msg = False
        for item in items:
            sku = item.get("merchantProductVariantReferenceKey", "")
            if sku not in tax_dict.keys():
                tax_dict[sku] = item.get("tax")
                continue
            if item.get("tax") == tax_dict[sku]:
                continue
            msg = _(
                "Two lines of the same item %s have different taxes applied, "
                "please check." % item.get("orderItemId", "")
            )
            _logger.warning(msg)
            break
        if msg:
            return msg
        return False

    def check_sale_order(self, data, external_id, backend):
        scayle_sale_order = (
            request.env["scayle.sale.order"]
            .sudo()
            .search_count(
                [
                    ("external_id", "=", external_id),
                    ("backend_id", "=", backend.id),
                ]
            )
        )
        if scayle_sale_order:
            _logger.warning(
                "The sale order is already imported, Please find OrderId reference: %s"
                % (external_id)
            )
            msg = self._duplicate_msg
            return msg

        reference_key = data.get("customer").get("referenceKey")
        email = data.get("customer").get("email")
        if not email:
            _logger.warning(
                "Customer email is missing from the payload, "
                "Please find OrderId reference: %s" % (external_id)
            )
            msg = _(
                "Customer email is missing from the payload for 'referenceKey' %s."
                % (reference_key)
            )
            return msg
        shipping_address = data.get("addresses").get("shipping")
        msg = self.validate_address(address=shipping_address, address_type="shipping")
        if msg:
            _logger.warning(
                "Received shipping address is invalid, "
                "some required fields are missing, Please find OrderId reference: %s"
                % (external_id)
            )
            return msg
        # T-02494 : Add validation if the scayle backend has "Required Phone Number" set
        # then check if the shipping address from the payload has no phone number, and
        # also verify that the PhoneNumber is valid.
        phone_number = shipping_address.get("phoneNumber")
        if backend.is_phonenumber_required and not phone_number:
            msg = "Phone Number Is missing from Shipping Address."
            _logger.warning(
                "Phone Number Is missing from Shipping Address."
                " Please find OrderId reference: %s",
                external_id,
            )
            return _(msg)
        if not data.get("items"):
            _logger.warning(
                "Items is missing/empty in the payload, "
                "Please find OrderId reference: %s" % (external_id)
            )
            msg = _("Items is missing/empty in the payload.")
            return msg

        order_item_ids = [item.get("orderItemId") for item in data.get("items")]
        duplicate_order_item_ids = list(
            {
                order_item_id
                for order_item_id in order_item_ids
                if order_item_ids.count(order_item_id) > 1
            }
        )
        if duplicate_order_item_ids:
            _logger.error(
                "The duplicate orderItemId are found in payload, "
                "Please find OrderId reference: %s" % (external_id)
            )
            raise ValidationError(
                _(
                    "The duplicate orderItemId found in payload. "
                    "They are : %(duplicate_ids)s"
                )
                % {"duplicate_ids": ",".join(duplicate_order_item_ids)}
            )

        no_product_reference_key = [
            item.get("orderItemId")
            for item in data.get("items")
            if not item.get("merchantProductVariantReferenceKey")
        ]
        if no_product_reference_key:
            _logger.warning(
                "The 'merchantProductVariantReferenceKey' is missing in items ids, "
                "Please find OrderId reference: %s" % (external_id)
            )
            msg = _(
                "The 'merchantProductVariantReferenceKey' is missing in items ids : %s."
                % ((",").join(no_product_reference_key))
            )
            return msg

        product_reference_key = [
            item.get("merchantProductVariantReferenceKey")
            for item in data.get("items")
            if item.get("merchantProductVariantReferenceKey")
        ]
        products = (
            request.env["product.product"]
            .sudo()
            .search(
                [
                    (
                        "default_code",
                        "in",
                        product_reference_key,
                    )
                ]
            )
        )
        no_reference_key = list(
            set(product_reference_key) - set(products.mapped("default_code"))
        )
        if no_reference_key:
            msg = _(
                "Product not found with default code"
                " (merchantProductVariantReferenceKey) %s in odoo."
                % ((",").join(no_reference_key))
            )
            _logger.warning(msg)
            return msg

        key = data.get("carrier").get("key", "").strip()
        if not key:
            _logger.warning(
                "Carrier key is missing in the payload, "
                "Please find OrderId reference: %s" % (external_id)
            )
            msg = _("Carrier key is missing in the payload.")
            return msg

        # T-02917 Add validation for phone number is always requires
        # for DHL Express shipping method.
        if key.lower() == "express" and not phone_number:
            msg = (
                "Phone Number is missing from Shipping Address and it is "
                f"required for '{key}' carrier. "
                f"Please find OrderId reference: {external_id}"
            )
            _logger.warning(msg)
            return _(msg)
        # T-02506 - Collection Point Shipping Address for DHL
        # Checked for collectionpoint is dict as "None" or "null" can be present as
        # value
        if shipping_address:
            msg = self.check_collectionpoint_of_shipping(
                shipping_address=shipping_address, key=key, external_id=external_id
            )
            if msg:
                return msg
        return

    def check_collectionpoint_of_shipping(self, shipping_address, key, external_id):
        if shipping_address.get("collectionPoint", {}) and isinstance(
            shipping_address.get("collectionPoint"), dict
        ):
            shipping_method = (
                request.env["delivery.carrier"]
                .sudo()
                .search(
                    [
                        ("eshop_carrier_code", "=ilike", key.upper()),
                        ("shipment_options", "=", "collection_point_delivery"),
                    ],
                    limit=1,
                )
            )
            if shipping_method and shipping_method.required_attributes:
                collection_point = shipping_address.get("collectionPoint", {})
                required_attributes = shipping_method.required_attributes.split(",")

                def check_required_key_value(key):
                    if not collection_point.get(key, "").strip():
                        return key

                missing_attributes = list(
                    filter(
                        lambda x: x is not None,
                        map(check_required_key_value, required_attributes),
                    )
                )
                if missing_attributes:
                    _logger.warning(
                        "'{}' is missing in the payload in shipping address"
                        " collectionPoint for type carrier {}."
                        "Please find OrderId reference: {}".format(
                            ",".join(missing_attributes),
                            key,
                            external_id,
                        )
                    )
                    msg = _(
                        "'%(missing_attributes)s' key or value is missing in the "
                        "payload in shipping address collectionPoint for type "
                        "carrier %(key)s."
                    ) % {
                        "missing_attributes": ", ".join(missing_attributes),
                        "key": key,
                    }

                    return msg
        return

    @http.route(
        [
            "/api/scayle/v1/order-create",
            "/api/scayle/v1/order-create/<access_token>",
        ],
        auth="public",
        type="json",
        methods=["POST"],
    )
    def import_scayle_order(self, access_token=None):
        """#T-02076 Create API to create order in odoo with scayle data"""
        data = request.get_json_data()
        try:
            access_token = get_access_token(
                access_token=access_token, header=request.httprequest.headers
            )
            if not access_token:
                _logger.error("No access token supplied!")
                raise ValidationError(_("No access token supplied!"))
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
                        (
                            "test_odoo_scayle_token",
                            "=",
                            f"{access_token}",
                        ),
                        ("test_mode", "=", True),
                        # T-02402 scayle.backend search with some extra fields
                        # code,shop_id and shop_key fields.
                        ("code", "=ilike", data.get("countryCode")),
                        ("shop_key", "=ilike", data.get("shopKey")),
                        ("shop_id", "=ilike", data.get("shopId")),
                    ],
                    limit=1,
                )
            )
            if not backend:
                shopKey = data.get("shopKey")
                countryCode = data.get("countryCode")
                shopId = data.get("shopId")
                _logger.error(
                    "The Combination of Access Token({}), ShopKey({}), CountryCode({}),"
                    "and ShopId({}) is Invalid!".format(
                        access_token, shopKey, countryCode, shopId
                    )
                )
                raise ValidationError(
                    _(
                        "The Combination of Access Token (%(access_token)s), ShopKey "
                        "(%(shopKey)s), CountryCode (%(countryCode)s), and ShopId "
                        "(%(shopId)s) is Invalid!"
                    )
                    % {
                        "access_token": access_token,
                        "shopKey": shopKey,
                        "countryCode": countryCode,
                        "shopId": shopId,
                    }
                )

            if not backend.order_creation_endpoint:
                _logger.info("Order creation endpoint is disabled")
                raise ValidationError(_("Order creation endpoint is disabled"))
            if backend.debug_mode:
                _logger.info("\n\nResult : \n%s\n" % pprint.pformat(data))
            message = self.get_error_message(data=data, backend=backend)  # T-02076
            external_id = data.get("orderId", False)
            if message:
                backend.with_delay(
                    priority=5,
                    description="Import Record: Scayle Sale Order",
                    identity_key=identity_exact,
                ).refused_order_delegation(message, external_id)
                if backend.return_valid_if_exists and message == self._duplicate_msg:
                    return {
                        "referenceKey": external_id,
                        "statusCode": 201,
                        "orderDelegationResult": "acknowledged",
                    }
                response = {
                    "statusCode": 400,
                    "errorKey": "validation_error",
                    "message": message,
                    "context": {"referenceKey": external_id},
                }
                return response
        except Exception:
            _logger.error(
                "Uncaught error during order import: {error}. Received response:{data}"
            )
            raise

        urls_to_forward_data = backend.scayle_url_ids.mapped("url")
        request.env["scayle.sale.order"].with_user(SUPERUSER_ID).with_company(
            backend.sudo().company_id
        ).with_delay(
            priority=3,
            description=backend.get_queue_job_message(model_name="scayle.sale.order"),
            identity_key=identity_exact,
        ).import_record(backend=backend, external_id=external_id, data=data)
        if backend.test_mode and urls_to_forward_data:
            # T-02536  The reason to put the below method on the backend is that,
            # we have to execute job as superuser (with_user(SUPERUSER_ID))
            # and here, self doesn't contains 'with_user' method.
            for url in urls_to_forward_data:
                backend.with_user(SUPERUSER_ID).with_company(
                    backend.sudo().company_id
                ).with_delay(identity_key=identity_exact).forward_data_to_scayle_url(
                    url=url.strip(), data=data
                )
        return {
            "referenceKey": external_id,
            "statusCode": 201,
            "orderDelegationResult": "acknowledged",
        }
