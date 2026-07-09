import logging

import werkzeug
from werkzeug.wrappers import Response

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class OpenInOdooController(http.Controller):
    @http.route(
        "/api/eshop/v1/open-order/<external_id>/",
        auth="user",
        type="http",
    )
    def open_so_in_odoo(self, external_id=None):
        """
        #T-02741: Controller to open sale order base on access token
        and external id.
        """
        if not external_id:
            _logger.error("No external ID supplied!")
            return Response(status=403)
        # Search for sale order binding using external id and backend IDs
        so_binding = (
            request.env["scayle.sale.order"]
            .sudo()
            .search(
                [
                    ("external_id", "=", external_id),
                ],
                limit=1,
            )
        )

        if not so_binding:
            _logger.error(f"Sale order not found for the external Id {external_id}!")
            return Response(status=404)

        # Redirect to the sale order form view
        return werkzeug.utils.redirect(
            f"/web#id={so_binding.odoo_id.id}&model=sale.order&view_type=form"
        )
