import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    """#T-02803 Migration Method, to set the language and order url at scayle backend"""

    # Define the mapping of country codes to URLs and languages
    country_configurations = [
        {
            "country_code": "PL",
            "senders7_order_url": "https://www.fielmann.pl",
            "senders7_language": "pl",
        },
        {
            "country_code": "CZ",
            "senders7_order_url": "https://www.fielmann.cz",
            "senders7_language": "cs",
        },
        {
            "country_code": "NL",
            "senders7_order_url": "https://www.lensplaza.com",
            "senders7_language": "nl",
        },
        {
            "country_code": "BE",
            "senders7_order_url": "https://www.lensplaza.com/be_nl/",
            "senders7_language": "nl",
        },
    ]
    # Iterate through each configuration and update the Scayle backend
    for config in country_configurations:
        _logger.info(
            f"Started Updating Scayle backend for country code {config['country_code']}"
        )
        env.cr.execute(
            """
            UPDATE scayle_backend
            SET
                senders7_order_url = %(senders7_order_url)s,
                senders7_language = %(senders7_language)s
            WHERE
                code = %(country_code)s;
            """,
            {
                "senders7_order_url": config["senders7_order_url"],
                "senders7_language": config["senders7_language"],
                "country_code": config["country_code"],
            },
        )
        _logger.info(
            f"Finished Updating Scayle backend for country "
            f"code {config['country_code']}"
        )

    # set language and order url for CH backends
    country_configurations_CH = [
        {
            "backend_name": "Scayle CH - DE",
            "senders7_order_url": "https://www.fielmann.ch",
            "senders7_language": "de",
        },
        {
            "backend_name": "Scayle CH - IT",
            "senders7_order_url": "https://www.fielmann.ch",
            "senders7_language": "it",
        },
        {
            "backend_name": "Scayle CH - FR",
            "senders7_order_url": "https://www.fielmann.ch",
            "senders7_language": "fr",
        },
    ]

    for config in country_configurations_CH:
        _logger.info(
            f"Started Updating Scayle backend for CH backend {config['backend_name']}"
        )
        env.cr.execute(
            """
            UPDATE scayle_backend
            SET
                senders7_order_url = %(senders7_order_url)s,
                senders7_language = %(senders7_language)s
            WHERE
                name = %(backend_name)s;
            """,
            {
                "senders7_order_url": config["senders7_order_url"],
                "senders7_language": config["senders7_language"],
                "backend_name": config["backend_name"],
            },
        )
        _logger.info(
            f"Finished Updating Scayle backend for CH backend {config['backend_name']}"
        )
