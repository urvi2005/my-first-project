**Connector Scayle**
====================

**Description**
***************

* Technical name: connector_scayle.
* Add mapping of product through scayle API.
* Add Sale order import through scayle API.
* Add Partner import through scayle API.
* Add Fulfillment export through scayle API.


**Author**
**********

* Pledra


**Used by**
***********

* Pledra


**Installation**
****************

* Under applications, the application connector_scayle can be installed/uninstalled.


**Configuration**
*****************

* Connector > Connector > Scayle Backend > Add the API configuration.
* Add default carrier in the scayle backend
* Setup the chart of account for company
* If multi-company, create different backend for each company and set company_id in the backend.


**Usage**
*********

* #T-02041 : Scayle Connector : Integrate the scayle with odoo and import/export partner, order, product, refund etc.
* #T-02052 - Scayle stock endpoint : Export to create product stock information on scayle.
    - Add field scayle warehouse reference key in warehouse to mapped the odoo warehouse to scayle manually.
    - Add the controller with parameters from_date and warehouse_reference_key which they will send.
    - It will search the product records with inventory_update_date from date to current date and export the product stock information on scayle.

* #T-02079 : Scayle Connector : sellableWithoutStock field.
    - Add Boolean(SWS) field on product.category level.
    - Add Selection(Yes/No/From Category) and Boolean(SWS --> compute field) on product.product level.
    - Add smart button on the product category level which will displays product which SWS Logic value have not from_category.
    - For the computed boolean field
        - if SWS Logic have "Yes" than Boolean is True.
        - if SWS Logic have "No" than Boolean is False.
        - if SWS Logic have "From Category" than Boolean value is based on the boolean field of product category level.
* #T-02076 : Scayle Connector : Scayle order import with controller
    - Create new controller "OrderImportEndPointController".
    - In controller use orderID(of payload) as external_id and import record(order)
      based on same.
    - Done changes in some mapping of fields, use orderID for SO, use orderItemId for
      SOL, use merchantProductVariantReferenceKey for product etc as per new payload.
    - Assign the sale order import to root.scayle queue.job channel.
    - Added Job function from queue.job for order creation.

* #T-02084 - Scayle connector: Order Cancelled : Cancelled order on scayle if cancelled in odoo.

* #T-02085 - Scayle connector: Create Shipment : Create shipment for delivery order(Export) on
             scayle.

* #T-02101 - Scayle connector: export return order : Return delivery order items on scayle.
    - shipment_key : delivery return order odoo id

* #T-02113 - Scayle Connector: Group per so line from scayle order import:
    - Scayle Data : Product A - qty - 1, Product B - qty -1, Product A - qty - 1.
    - If we import scayle data in odoo it will group the product and add in line.
    - In Odoo -  Product A - qty - 2, Product B - qty -1.

* #T-02155 - Scayle connector: Chatter messages & fields:
    - Add the selection fields for shipment / cancelled / return sync to scayle instead of boolean.
    - Add the tracking on (shipment / return) selection field to have track in chatter at the sale order level.
    
* #T-02156 - Access rights errors:
    - Hide scayle backend probably for main company.
    - Add connector manager rights for stock picking scayle inherit views.
    - Add sudo to backend id for scayle.

* #T-02212 - Update inventory_update_date based on Scayle SWS field:
    - Add inverse method for scayle_sws_logic field to update inventory_update_date.
    - inventory_update_date is updated if the stock move is in done state, and the product
      it contains must have scayle_sws field value False.
    - Remove _compute_scayle_sws method of product

* #T-02331 - Multiwarehouse stock update & SWS:
    - Add new object stock_update_dates and add m2o of warehouse, product.
    - Add inventory_update_date and sws_update_date in stock_update_dates model.
    - Add o2m of stock_update_dates at product_variant level in Scayle Connector tab.
    - Add button at warehouse level "Generic Missing Inventory Dates" to add missing stock_update_dates
      model in product.
    - Updating sws_update_date from the product category based on scayle_sws_logic field.
    - Updating the inventory_update_date of stock.update.date model if the onhand quantity of product is updated.

* #T-02250 - Automated tests: Connector Scayle
    - Automated tests for connector scayle including controllers

* #T-02471 - Scayle connector: Add the "Open in Scayle" button on header

* #T-02494 - T-02494 - Everstox connector: phone number
    - Validate the scayle sale order from controller if the "Required Phone Number" is set.

* #T-02496 - Scayle connector: Debug mode in backend for logger
    - Add Debug mode in backend scayle and if debug mode is True then log the URL, Argument/parameters, Data from the webhook and result from the adaptar.

* #T-02320 - Config data History Line
    - api_payload_history_ids to keep track of all the responses coming from scayle for sale order and stock picking

* #T-02557 - Remove Lot Support, Comment Code, and Migrate Old Records
    - Remove the lot related logic.
    
* #T-02583 - Scayle connector: Split stock quantity (Webhook)
    - New Object: eshop.stock.ratio(fields: scayle_backend_id, percentage,product_categ_id, min_qty)
    - New O2M is added to category(eshop_stock_ratio_ids) for eshop.stock.ratio.
    - While hitting the endpoint of stock update, it returns the sellable value of the quantity
    - i.e. (product's sellable quantity * percentage /100)
    - If the relevant backend not found, then it get the value from the field of product.category
      which is 'Default Available Stock'.
    - If the percentage is calculated via o2m fields, the quantity value should be round down.
    - If the percentage is calculated via new field of category, the quantity value should be round up.
    - Check min_qty in webhook. If particular ratio found in webhook and the min_qty of that ratio is higher than the product sellable quantity,(that is on_hand_qty-outgoing qty), we have to send the 0 into the sellableQuantity and quantity.
    
* #T-02556 - Intercompany Logic Removal and Implementation of Direct Main Order Process
    - Stop the creation of sub-company sale order and also inter-company flow.
    - At sale order line from now on price unit will be fetched from product's lst_price.

**Known issues/Roadmap**
************************

* #N/A


**Changelog**
*************

* #N/A
