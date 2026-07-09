import logging

from odoo.addons.component.core import AbstractComponent
from odoo.addons.connector_base_ecommerce.components.backend_adapter import (
    BaseEcommerceAPI,
    BaseEcommerceClient,
    BaseEcommerceLocation,
)

_logger = logging.getLogger(__name__)


class ScayleLocation(BaseEcommerceLocation):
    @property
    def location(self):
        """Return the remote location/URL for scayle"""
        location = f"{self._location}"
        if not location.endswith("/"):
            location = f"{location}/"
        return location


class ScayleClient(BaseEcommerceClient):
    """
    The Class is used to sends request/get response in json data.
    (for eg : order data, customer data)
    """


class ScayleAPI(BaseEcommerceAPI):
    @property
    def api(self):
        """Config the API values"""
        if self._api is None:
            scayle_client = ScayleClient(
                self._location.location,
                self._location.token,
                self._location.version,
                self._location.test_mode,
                debug_mode=self._location.debug_mode,
            )
            self._api = scayle_client
        return self._api


class ScayleCRUDAdapter(AbstractComponent):
    """External Records Adapter for Scayle"""

    # pylint: disable=method-required-super

    _name = "scayle.crud.adapter"
    _inherit = ["base.ecommerce.crud.adapter", "base.scayle.connector"]
    _usage = "backend.adapter"

    def search(self, filters=None):
        """
        Search records according to some criterias
        and returns a list of ids
        """
        raise NotImplementedError

    def read(self, external_id, attributes=None):
        """Returns the information of a record"""
        raise NotImplementedError

    def search_read(self, filters=None):
        """
        Search records according to some criterias
        and returns their information
        """
        raise NotImplementedError

    def create(self, data):
        """Create a record on the external system"""
        raise NotImplementedError

    def write(self, external_id, data):
        """Update records on the external system"""
        raise NotImplementedError

    def delete(self, external_id):
        """Delete a record on the external system"""
        raise NotImplementedError

    def cancel(self, external_id, **kwargs):
        """Cancel a record on the external system"""
        raise NotImplementedError

    def get_token(self, arguments=None, http_method=None):
        """Method to get token from remote system"""
        return self._call(
            resource_path=None,
            arguments=arguments,
            http_method=http_method,
            is_token=True,
        )


class GenericAdapter(AbstractComponent):
    # pylint: disable=method-required-super

    _name = "scayle.adapter"
    _inherit = "scayle.crud.adapter"

    _eshop_model = None
    _eshop_model_cancel = None
    _eshop_model_extension = None
    _eshop_create_model = None

    _eshop_ext_id_key = "id"

    def search(self, filters=None):
        """
        Returns the information of a record

        :rtype: dict
        """
        resource_path = self._eshop_model
        result = self._call(resource_path, arguments=filters)
        return result

    def search_read(self, filters=None):
        """
        Search records according to some criteria
        and returns their information
        """
        resource_path = self._eshop_model
        result = self._call(resource_path, arguments=filters)
        return result

    def read(self, external_id=None, attributes=None):
        """
        Returns the information of a record

        :rtype: dict
        """
        resource_path = self._eshop_model
        if external_id:
            resource_path = f"{resource_path}/{external_id}"
        result = self._call(resource_path)
        return result

    def create(self, data):
        """Create a record on the external system"""
        resource_path = self._eshop_create_model
        result = self._call(resource_path, data, http_method="post")
        return result

    def write(self, external_id, data):
        """Update records on the external system"""
        resource_path = self._eshop_model
        resource_path = f"{resource_path}/{external_id}"
        if self._eshop_model_extension:
            resource_path = f"{resource_path}/{self._eshop_model_extension}"
        http_method = self._http_update_method
        result = self._call(resource_path, data, http_method=http_method)
        return result

    def delete(self, external_id):
        """Delete a record on the external system"""
        resource_path = self._eshop_model
        resource_path = f"{resource_path}/{external_id}"
        result = self._call(resource_path, http_method="delete")
        return result
