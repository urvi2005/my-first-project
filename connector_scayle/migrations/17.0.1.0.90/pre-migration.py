import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    """#T-3107 : Added migration script to Update blacklist email template."""
    _logger.info("Started Updating blacklist email template")
    # T-3107 product template to delete
    product_email_template = env.ref(
        "connector_scayle.email_template_blacklist_product",
        raise_if_not_found=False,
    )

    if product_email_template:
        product_email_template.unlink()
        _logger.info(
            "Deleted connector_scayle.email_template_blacklist_product template."
        )
    customer_email_template = env.ref(
        "connector_scayle.email_template_blacklist_customer",
        raise_if_not_found=False,
    )

    if not customer_email_template:
        _logger.warning(
            "Template connector_scayle.email_template_blacklist_customer not found."
        )
        return

    customer_email_template.write(
        {
            "body_html": """
<div style="margin: 0px; padding: 0px; font-family: sans-serif;">
    <p style="margin:0px 0 0px 0;box-sizing:border-box;margin-bottom: 0px;">
    </p>
    <p style="box-sizing:border-box;margin:0 0 10px 0;">
        Hello,<br /><br />
        The following sales order has been
        &lt;strong&gt;flagged as blacklisted&lt;/strong&gt;
        and requires your attention:<br/>
        Order: <t t-out="object.name"></t><br />
        Customer: <t t-out="object.partner_shipping_id.name"></t><br />
        Total Amount: <t t-out="object.amount_total"></t><br />
        Order Date: <t t-out="object.create_date"></t><br /><br />
        <t t-if="ctx.get('blacklist_filters')">
            <strong>Matched Blacklist Filters:</strong>
        </t>
        <ul>
            <t
                t-foreach="ctx.get('blacklist_filters', [])"
                t-as="filter_name"
            >
                <li>
                    <t t-out="filter_name"></t>
                </li>
            </t>
        </ul>
        <t t-if="ctx.get('blacklist_filters')">
            <strong>Blacklist Reasons:</strong>
        </t>
        <ol>
            <t t-if="ctx.get('blacklist_customer')">
                <li>Customer is blacklisted.</li>
            </t>
            <t t-if="ctx.get('blacklist_products')">
                <li>
                    Blacklisted Products:
                    <br />
                    <t
                        t-foreach="ctx.get('blacklist_products', [])"
                        t-as="product"
                    >
                        <strong>Frame Product (Blacklisted):</strong>
                        <br />-
                        <t t-out="product.get('frame_product')"></t>
                        <br />
                        <strong>Related Finished Products:</strong>
                        <t
                            t-foreach="product.get('finished_products', [])"
                            t-as="finished_product"
                        >
                            <br />-
                            <t t-out="finished_product"></t>
                        </t>
                        <br /><br />
                    </t>
                </li>
            </t>
        </ol>
        You can view the full order details by clicking the button below:
        <br />
    </p>
    <p style="margin:0px 0 0px 0;box-sizing:border-box;margin-bottom: 0px;">
        <a
            t-att-href="
                object.get_base_url()
                + '/web#id=' + str(object.id)
                + '&amp;model=' + object._name
                + '&amp;view_type=form'
            "
            target="_blank"
            style="
                margin:8px 0 0 0;
                box-sizing:border-box;
                display:inline-block;
                padding:10px 16px;
                margin-top:8px;
                background-color:#875A7B;
                color:#ffffff;
                border-radius:6px;
                text-decoration:none;
                font-weight:bold;
                font-size:13px;
            "
        >
            Open Order in Odoo
        </a>
    </p>
    <p style="margin:0px 0 0px 0;box-sizing:border-box;margin-bottom: 0px;">
        <br />
    </p>
    <p style="margin: 0px; box-sizing: border-box;">
        Thank you!
    </p>
    <p style="margin:0px 0 0px 0;box-sizing:border-box;margin-bottom: 0px;">
        <br />
    </p>
</div>
""",
        }
    )

    _logger.info("Finished updating email_template_blacklist_customer template.")
