{
    "name": "Connector Scayle",
    "summary": """
        Integration of Scayle Connector with Odoo
    """,
    "author": "Pledra",
    "license": "AGPL-3",
    "website": "http://www.pledra.com",
    "category": "Connector",
    "version": "17.0.1.0.91",
    "depends": [
        "product",
        "sale_stock",
        "stock_delivery",  # ADD T-02726 to resolve js error for hsn code
        "purchase",
        "api_payload_history",
        "queue_job_related_action",
        "connector_base_ecommerce",
        "connector_base_pim",
        "stock_split_picking",
        "fielmann_sale_workflow",
        "fielmann_stock_reserve",  # T-02935 to create reservations
    ],
    # always  loaded
    "data": [
        "security/eshop_cancellation_security.xml",  # T-03065
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "data/queue_job_data.xml",
        "data/ir_config_param_data.xml",
        "data/mail_template_data.xml",  # T-02935
        "views/scayle_shop_views.xml",
        "views/blacklisted_customer_views.xml",  # T-02935
        "views/scayle_url_views.xml",  # T-02536
        "views/scayle_sale_order_line.xml",  # T-03065
        "views/scayle_backend_views.xml",
        "views/res_partner_views.xml",
        "views/connector_scayle_menus.xml",
        "views/sale_order_view.xml",
        "views/stock_picking_views.xml",
        "views/sale_order_line_view.xml",
        "wizard/replacement_order_view.xml",
    ],
    # only loaded in demonstration mode
    "demo": ["demo/demo_product_variants.xml"],
}
