import logging

import requests

import advisory
import authorization
import config
import constants
import rest_api
import json

ADV_TOKENS = constants.ADVISORY_FORMAT_TOKENS

TEMPORAL_FILTER_KEYS = ('startDate', 'endDate')
PUBLISHED_FIRST = 'firstpublished'
PUBLISHED_LAST = 'lastpublished'
TEMPORAL_PUBLICATION_ASPECTS = (PUBLISHED_FIRST, PUBLISHED_LAST)


def ensure_adv_format_token(adv_format):
    """Map cvrf, oval, anything to cvrf, oval, ios - just DRY."""
    return adv_format if adv_format in ADV_TOKENS else ADV_TOKENS[-1]


class Filter(object):
    def __init__(self, path='', params=None):
        self.path = path
        self.params = params


class TemporalFilter(object):
    def __init__(self, path, *args):
        self.path = path  # Better be in TEMPORAL_PUBLICATION_ASPECTS ...
        self.params = dict(zip(TEMPORAL_FILTER_KEYS, args))


class FirstPublished(TemporalFilter):
    def __init__(self, *args):
        super(FirstPublished, self).__init__(PUBLISHED_FIRST, *args)


class LastUpdated(TemporalFilter):
    def __init__(self, *args):
        super(LastUpdated, self).__init__(PUBLISHED_LAST, *args)


class OpenVulnQueryClient(object):
    """Client sends get request for advisory information from OpenVuln API.

    :var auth_token: OAuth2 Token for API authorization.
    :var headers: Headers containing OAuth2 Token and data type for
     request.
    """

    def __init__(self, client_id, client_secret, auth_url=None,
                 user_agent='TestApp'):
        """
        :param client_id: Client application Id as retrieved from API provider
        :param client_secret: Client secret as retrieved from API provider
        :param auth_url: POST URL to request auth token response (default
            from config)
        :param user_agent: Communicates the name of the app per request.

        """
        logging.basicConfig(level=logging.WARNING)
        self.logger = logging.getLogger(__name__)
        self.auth_url = auth_url if auth_url else config.REQUEST_TOKEN_URL
        self.auth_token = authorization.get_oauth_token(
            client_id, client_secret, request_token_url=self.auth_url)
        self.headers = rest_api.rest_with_auth_headers(
            self.auth_token, user_agent)

    def get_by_all(self, adv_format, all_adv, a_filter):
        """Return all the advisories using requested advisory format"""
        req_cfg = {
            'adv_format': ensure_adv_format_token(adv_format),
            'all': all_adv,
            'filter': a_filter.path,
        }
        req_path = "{adv_format}/{all}/{filter}".format(**req_cfg)
        advisories = self.get_request(req_path, a_filter.params)
        return self.advisory_list(advisories['advisories'], adv_format)

    def get_by_cve(self, adv_format, cve, a_filter=None):
        """Return the advisory using requested cve id"""
        req_cfg = {
            'adv_format': ensure_adv_format_token(adv_format),
            'cve': cve,
        }
        req_path = "{adv_format}/cve/{cve}".format(**req_cfg)
        advisories = self.get_request(req_path)
        return self.advisory_list(advisories['advisories'], adv_format)

    def get_by_advisory(self, adv_format, an_advisory, a_filter=None):
        """Return the advisory using requested advisory id"""
        req_cfg = {
            'adv_format': ensure_adv_format_token(adv_format),
            'advisory': an_advisory,
        }
        req_path = "{adv_format}/advisory/{advisory}".format(**req_cfg)
        advisories = {'advisories': [self.get_request(req_path)]}
        return self.advisory_list(advisories['advisories'], adv_format)

    def get_by_severity(self, adv_format, severity, a_filter=None):
        """Return the advisories using requested severity"""
        req_cfg = {
            'adv_format': ensure_adv_format_token(adv_format),
            'severity': severity,
            'filter': Filter().path if a_filter is None else a_filter.path,
        }
        req_path = ("{adv_format}/severity/{severity}/{filter}"
                    "".format(**req_cfg))
        advisories = self.get_request(req_path, params=a_filter.params)
        return self.advisory_list(advisories['advisories'], adv_format)

    def get_by_year(self, adv_format, year, a_filter=None):
        """Return the advisories using requested year"""
        req_cfg = {
            'adv_format': ensure_adv_format_token(adv_format),
            'year': year,
        }
        req_path = "{adv_format}/year/{year}".format(**req_cfg)
        advisories = self.get_request(req_path)
        return self.advisory_list(advisories['advisories'], adv_format)

    def get_by_latest(self, adv_format, latest, a_filter=None):
        """Return the advisories using requested latest"""
        req_cfg = {
            'adv_format': ensure_adv_format_token(adv_format),
            'latest': latest,
        }
        req_path = "{adv_format}/latest/{latest}".format(**req_cfg)
        advisories = self.get_request(req_path)
        return self.advisory_list(advisories['advisories'], adv_format)

    def get_by_product(self, adv_format, product_name, a_filter=None):
        """Return advisories by product name"""
        req_cfg = {
            'adv_format': ensure_adv_format_token(adv_format),
        }
        req_path = "{adv_format}/product".format(**req_cfg)
        advisories = self.get_request(
            req_path, params={'product': product_name})
        return self.advisory_list(advisories['advisories'], adv_format)

    def get_by_ios_xe(self, adv_format, ios_version, a_filter=None):
        """Return advisories by Cisco IOS advisories version"""
        req_path = "iosxe"
        try:
            advisories = self.get_request(
                req_path,
                params={'version': ios_version})
            return self.advisory_list(advisories['advisories'], None)
        except requests.exceptions.HTTPError as e:
            raise requests.exceptions.HTTPError(
                e.response.status_code, e.response.text)

    def get_by_ios(self, adv_format, ios_version, a_filter=None):
        """Return advisories by Cisco IOS advisories version"""
        req_path = "ios"
        try:
            advisories = self.get_request(
                req_path,
                params={'version': ios_version})
            return self.advisory_list(advisories['advisories'], None)
        except requests.exceptions.HTTPError as e:
            raise requests.exceptions.HTTPError(
                e.response.status_code, e.response.text)

    def get_by(self, topic, format, aspect, **kwargs):
        """Cartesian product ternary paths biased REST dispatcher."""
        trampoline = {  # key: function; required and [optional] parameters
            'all': self.get_by_all,  # format, all_adv, a_filter
            'cve': self.get_by_cve,  # format, cve, [a_filter]
            'advisory': self.get_by_advisory,  # format, an_advisory,[a_filter]
            'severity': self.get_by_severity,  # format, severity, [a_filter]
            'year': self.get_by_year,  # format, year, [a_filter]
            'latest': self.get_by_latest,  # format, latest, [a_filter]
            'product': self.get_by_product,  # format, product_name, [a_filter]
            'ios_xe': self.get_by_ios_xe,  # 'ios', ios_version, [a_filter]
            'ios': self.get_by_ios,  # 'ios', ios_version, [a_filter]
        }
        if topic not in trampoline:
            raise KeyError(
                "REST API 'topic' ({}) not (yet) supported.".format(topic))

        return trampoline[topic](format, aspect, **kwargs)

    def get_request(self, path, params=None):
        """Send get request to OpenVuln API utilizing headers.

        :param path: OpenVuln API path.
        :param params: url parameters
        :return JSON of requested arguments for advisory information.
        :raise HTTPError for anything other than a 200 response.
        """
        self.logger.info("Sending Get Request %s", path)
        req_cfg = {'base_url': config.API_URL, 'path': path}
        req_url = "{base_url}/{path}".format(**req_cfg)
        r = requests.get(
            url=req_url,
            headers=self.headers,
            params=params)
        r.raise_for_status()
        return r.json()

    def advisory_list(self, advisories, adv_format):
        """Converts json into a list of advisory objects.

        :param advisories: A list of dictionaries describing advisories.
        :param adv_format: The target format either in ('cvrf', 'oval') or
            something that evaluates to False (TODO HACK A DID ACK ?) for ios.
        :return list of advisory instances
        """
        adv_format = ensure_adv_format_token(adv_format)
        return [advisory.advisory_factory(adv, adv_format, self.logger)
                for adv in advisories]
