"""GreyNoise API client."""

import logging
import sys

import requests

from greynoise.exceptions import RequestFailure
from greynoise.util import (
    validate_date,
    validate_ip,
)


class GreyNoise(object):

    """Abstract interface for GreyNoise."""

    NAME = "GreyNoise"
    LOG_LEVEL = logging.INFO
    BASE_URL = "https://enterprise.api.greynoise.io"
    CLIENT_VERSION = 1
    API_VERSION = "v2"
    EP_NOISE_BULK = "noise/bulk"
    EP_NOISE_BULK_DATE = "noise/bulk/{date}"
    EP_NOISE_QUICK = "noise/quick/{ip_address}"
    EP_NOISE_MULTI = "noise/multi/quick"
    EP_NOISE_CONTEXT = "noise/context/{ip_address}"
    UNKNOWN_CODE_MESSAGE = "Code message unknown: {}"
    CODE_MESSAGES = {
        "0x00": "IP has never been observed scanning the Internet",
        "0x01": "IP has been observed by the GreyNoise sensor network",
        "0x02": (
            "IP has been observed scanning the GreyNoise sensor network, "
            "but has not completed a full connection, meaning this can be spoofed"
        ),
        "0x03": (
            "IP is adjacent to another host that has been directly observed "
            "by the GreyNoise sensor network"
        ),
        "0x04": "RESERVED",
        "0x05": "IP is commonly spoofed in Internet-scan activity",
        "0x06": (
            "IP has been observed as noise, but this host belongs to a cloud provider "
            "where IPs can be cycled frequently"
        ),
        "0x07": "IP is invalid",
        "0x08": (
            "IP was classified as noise, but has not been observed "
            "engaging in Internet-wide scans or attacks in over 60 days"
        ),
    }

    def __init__(self, api_key):
        """Init the object."""
        self._log = self._logger()
        self.api_key = api_key

    def _logger(self):
        """Create a logger to be used between processes.

        :returns: Logging instance.
        """
        logger = logging.getLogger(self.NAME)
        logger.setLevel(self.LOG_LEVEL)
        shandler = logging.StreamHandler(sys.stdout)
        fmt = "\033[1;32m%(levelname)-5s %(module)s:%(funcName)s():"
        fmt += "%(lineno)d %(asctime)s\033[0m| %(message)s"
        shandler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(shandler)
        return logger

    def set_log_level(self, level):
        """Set the log level."""
        if level == "info":
            level = logging.INFO
        if level == "debug":
            level = logging.DEBUG
        if level == "error":
            level = logging.ERROR
        self._log.setLevel(level)

    def _request(self, endpoint, params=None, json=None):
        """Handle the requesting of information from the API."""
        if params is None:
            params = {}
        headers = {
            "X-Request-Client": "pyGreyNoise v{}".format(self.CLIENT_VERSION),
            "key": self.api_key,
        }
        url = "/".join([self.BASE_URL, self.API_VERSION, endpoint])
        self._log.debug("Requesting: %s", url)
        response = requests.get(
            url, headers=headers, timeout=7, params=params, json=json
        )
        if response.status_code not in range(200, 299):
            raise RequestFailure(response.status_code, response.content)

        return response.json()

    def _recurse(self, config, breaker=False):
        results = None  # TODO: Where is results coming from?
        if breaker:
            return results
        kwargs = {"endpoint": config["endpoint"], "params": config["params"]}
        response = self._request(**kwargs)
        if not response["complete"]:
            config["results"].append(config["data_key"])
            self._recurse(config, response["complete"])

    def get_noise(self, date=None, recurse=True):
        """Get a complete dump of noisy IPs associated with Internet scans.

        Get all noise IPs generated by Internet scanners, search engines, and
        worms. Users will get all values or can specify a date filter for just
        a single day.

        :param date: Optional date to use as a filter.
        :type date: str
        :param recurse: Recurse through all results.
        :type recurse: bool
        :return: List of IP addresses associated with scans.
        :rtype: list
        """
        results = dict()
        endpoint = self.EP_NOISE_BULK
        if date:
            validate_date(date)
            endpoint = self.EP_NOISE_BULK_DATE.format(date=date)

        if recurse:
            config = {
                "endpoint": endpoint,
                "params": dict(),
                "results": list(),
                "data_key": "noise_ips",
            }
            results = self._recurse(config)
            return results

        response = self._request(endpoint)
        results["results"] = list(set(response["noise_ips"]))
        results["result_count"] = len(results["results"])
        return results

    def get_noise_status(self, ip_address):
        """Get activity associated with an IP address.

        :param ip_address: IP address to use in the look-up.
        :type recurse: str
        :return: Activity metadata for the IP address.
        :rtype: dict

        """
        validate_ip(ip_address)
        endpoint = self.EP_NOISE_QUICK.format(ip_address=ip_address)
        result = self._request(endpoint)
        code = result["code"]
        result["code_message"] = self.CODE_MESSAGES.get(
            code,
            self.UNKNOWN_CODE_MESSAGE.format(code),
        )
        return result

    def get_noise_status_bulk(self, ip_addresses):
        """Get activity associated with multiple IP addresses.

        :param ip_addresses: IP addresses to use in the look-up.
        :type ip_addresses: list
        :return: Bulk status information for IP addresses.
        :rtype: dict

        """
        if not isinstance(ip_addresses, list):
            raise ValueError("`ip_addresses` must be a list")

        ip_addresses = [
            ip_address
            for ip_address in ip_addresses
            if validate_ip(ip_address, strict=False)
        ]
        results = self._request(self.EP_NOISE_MULTI, json={"ips": ip_addresses})
        for result in results:
            code = result["code"]
            result["code_message"] = self.CODE_MESSAGES.get(
                code,
                self.UNKNOWN_CODE_MESSAGE.format(code),
            )
        return results

    def get_context(self, ip_address):
        """Get context associated with an IP address.

        :param ip_address: IP address to use in the look-up.
        :type recurse: str
        :return: Context for the IP address.
        :rtype: dict

        """
        validate_ip(ip_address)
        endpoint = self.EP_NOISE_CONTEXT.format(ip_address=ip_address)
        response = self._request(endpoint)
        return response
