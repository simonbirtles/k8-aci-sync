"""

TODO:
    Thread alive checking
    Graceful thread termination 
    Thread Locking vars: 
        managed_objects, apic_token, 

"""
import os
from time import sleep
import json
import re
import requests
from websocket import create_connection, WebSocketException
import urllib3
import ssl
import _thread

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    username = os.environ["ACI_USERNAME"]
    password = os.environ["ACI_PASSWORD"]
    host = os.environ["ACI_APIC"]
except KeyError as e:
    print("ACI APIC Environment Variable Missing.")
    raise

apic_token = None
token_refresh_time = None
websocket = None
subscription_ids = set()
subscription_refresh_time = 60


class REST_Error(Exception):
    """
    ACI APIC REST Error
    Contains additional attributes:
    - code: REST API Code
    - content: Raw content returned by REST API
    """

    def __init__(self, m, code, content):
        super().__init__(m)
        self.code = code
        self.content = content


def get_websocket():
    return websocket


def get_token():
    return apic_token


def login():

    global apic_token
    global token_refresh_time

    url = "https://{}/api/aaaLogin.json".format(host)
    payload = {"aaaUser": {"attributes": {"name": username, "pwd": password}}}
    headers = {"Content-Type": "application/json"}
    r = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
    if r.status_code != 200:
        raise Exception("APIC login failed with error: {}\n{}".format(r.status_code, r.content))

    data = json.loads(r.content)
    apic_token = {"APIC-cookie": r.cookies["APIC-cookie"]}
    token_refresh_time = data["imdata"][0]["aaaLogin"]["attributes"]["refreshTimeoutSeconds"]

    print("Logged into APIC")
    _thread.start_new_thread(login_refresh, ())
    open_websocket()


def login_refresh():
    """
    Dedicated Thread (from login())
    """
    global apic_token
    global token_refresh_time

    while True:
        sleep(min(60, int(token_refresh_time) / 2))
        r = requests.get(
            "https://{}/api/aaaRefresh.json".format(host), cookies=apic_token, verify=False
        )
        if r.status_code != 200:
            print(r.content)
            print("APIC session refresh failed")
            raise Exception(
                "APIC session refresh failed with {}-{}".format(r.status_code, r.content)
            )
        else:
            # print("APIC session refresh successful")
            apic_token = {"APIC-cookie": r.cookies["APIC-cookie"]}
            data = json.loads(r.content)["imdata"][0]
            token_refresh_time = data["aaaLogin"]["attributes"]["refreshTimeoutSeconds"]


def open_websocket():
    """ """
    global websocket
    kwargs = {"enable_multithread": True}
    sslopt = {"cert_reqs": ssl.CERT_NONE}
    assert apic_token is not None
    url = "wss://{}/socket{}".format(host, apic_token["APIC-cookie"])
    try:
        websocket = create_connection(url, sslopt=sslopt, **kwargs)
        if websocket.connected:
            print("APIC websocket created")
        else:
            print("APIC websocket creation failed.")
            raise Exception("APIC websocket creation failed.")

    except WebSocketException as wse:
        print("APIC Websocket Error with: {}".format(str(wse)))
        raise

    except socket.error as sockerror:
        print("APIC Websocket Error with: {}".format(str(sockerror)))
        raise


def logout():
    global apic_token
    url = "https://{}/api/aaaLogout.json".format(host)
    payload = {"aaaUser": {"attributes": {"name": username}}}
    headers = {"Content-Type": "application/json"}
    r = requests.post(
        url, headers=headers, data=json.dumps(payload), cookies=apic_token, verify=False
    )
    if r.status_code != 200:
        print("APIC logout failed with error: {}\n{}".format(r.status_code, r.content))

    apic_token = None
    print("Logged out of APIC")


def get(urlpath, query_filters=None):
    """
    ACI GET REST CALL


    urlpath:str e.g. /api/mo/uni/tn-TEN_K8/...
    query_filters:dict /

    Example of query_filters dict showing all possible options (each key is optional):


    {
        # Define the scope of a query - {self | children | subtree}
        "query-target"          : "subtree",

        # Respond-only elements including the specified class - 'class name'
        "target-subtree-class"  : "fvAEPg",

        # Respond-only elements matching conditions - filter expressions
        "query-target-filter"   : "",

        # Specifies child object level included in the response - {no | children | full}
        "rsp-subtree"           : "",

        # Respond only specified classes - 'class name'
        "rsp-subtree-class"     : "",

        # Respond only classes matching conditions - filter expressions
        "rsp-subtree-filter"    : "",

        # Request additional objects -{faults | health :stats :…}
        "rsp-subtree-include"   : "",

        # Sort the response based on the property values - classname.property | {asc | desc}
        "order-by"              : ""

        # Create a subscription for object events (created, modified, deleted) { yes | no}
        "subscription"          : ""

        # The ID of an existing subscription to renew
        "id"                    : int
    }

    returns:dict the full APIC response as json(dict)
    """
    _urlpath = urlpath if urlpath.startswith("/") else ("/" + urlpath)
    params = _format_query_filter(query_filters)
    headers = {"Content-Type": "application/json"}
    url = "https://{}{}.json{}".format(host, _urlpath, params)
    r = requests.get(url, headers=headers, cookies=apic_token, verify=False)

    if re.fullmatch(r"[345]..", str(r.status_code)):
        raise REST_Error(
            "APIC REST GET failed for {} with error: {}\n{}".format(url, r.status_code, r.content),
            code=r.status_code,
            content=r.content,
        )

    data = json.loads(r.content)
    return data


def delete(dn):
    """
    Delete APIC object by DN
    dn: e.g. /uni/tn-TEN_PROD/ctx-....
    """
    _dn = dn if dn.startswith("/") else ("/" + dn)
    url = "https://{}/api/mo{}.json?rsp-subtree=modified".format(host, _dn)
    # Returns 200 OK even if the object does not exist.. .but gives a 400
    # if DN url not in right format
    r = requests.delete(url, cookies=apic_token, verify=False)
    if re.fullmatch(r"[345]..", str(r.status_code)):
        raise REST_Error(
            "APIC REST DELETE failed for: {} with error: {}\n{}".format(
                url, r.status_code, r.content
            ),
            code=r.status_code,
            content=r.content,
        )
    print("Deleted MO with DN: {}".format(_dn))


def post(urlpath, payload, query_filters=None):
    """
    Returns modified object, full raw json content \
    
    urlpath:str e.g. /api/mo/uni/tn-TEN_K8/...
    payload:dict
    query_filters:dict 
    
    Example of query_filters dict showing all possible options (each key is optional):


    {
        # Define the scope of a query - {self | children | subtree}
        "query-target"          : "subtree",

        # Respond-only elements including the specified class - 'class name'
        "target-subtree-class"  : "fvAEPg",

        # Respond-only elements matching conditions - filter expressions
        "query-target-filter"   : "",

        # Specifies child object level included in the response - {no | children | full}
        "rsp-subtree"           : "",

        # Respond only specified classes - 'class name'
        "rsp-subtree-class"     : "",

        # Respond only classes matching conditions - filter expressions
        "rsp-subtree-filter"    : "",

        # Request additional objects -{faults | health :stats :…}
        "rsp-subtree-include"   : "",

        # Sort the response based on the property values - classname.property | {asc | desc}
        "order-by"              : ""
    }
    Raises: 
    
    - REST_Error with for non REST 2xx code with additional attributes 'code' and 'content'

    """
    if "api/mo/" not in urlpath and "api/class/" not in urlpath:
        raise Exception("The urlpath does not have /api/..../ prefix. {}".format(urlpath))

    _urlpath = urlpath if urlpath.startswith("/") else ("/" + urlpath)

    _query_filters = query_filters.copy() if query_filters is not None else {}
    # always return full object not just modified for this
    # application, does include children as well which is a shame
    # but we do rely on the full object being returned or its
    # another call to get the full object.
    _query_filters["rsp-subtree"] = "full"
    params = _format_query_filter(_query_filters)
    headers = {"Content-Type": "application/json"}
    url = "https://{}{}.json{}".format(host, _urlpath, params)
    r = requests.post(
        url, headers=headers, data=json.dumps(payload), cookies=apic_token, verify=False
    )
    if re.fullmatch(r"[345]..", str(r.status_code)):
        raise REST_Error(
            "APIC REST POST failed for {} with error: {}\n{}".format(url, r.status_code, r.content),
            code=r.status_code,
            content=r.content,
        )

    data = json.loads(r.content)
    return data


def _format_query_filter(query_filters):
    """
    build a valid APIC query string from passed dict

    query_filters:dict

    Example of query_filters dict showing all possible options (each key is optional):
    {
        # Define the scope of a query - {self | children | subtree}
        "query-target"          : "subtree",

        # Respond-only elements including the specified class - 'class name'
        "target-subtree-class"  : "fvAEPg",

        # Respond-only elements matching conditions - filter expressions
        "query-target-filter"   : "",

        # Specifies child object level included in the response - {no | children | full}
        "rsp-subtree"           : "",

        # Respond only specified classes - 'class name'
        "rsp-subtree-class"     : "",

        # Respond only classes matching conditions - filter expressions
        "rsp-subtree-filter"    : "",

        # Request additional objects -{faults | health :stats :…}
        "rsp-subtree-include"   : "",

        # Sort the response based on the property values - classname.property | {asc | desc}
        "order-by"              : ""

        # Create a subscription for object events (created, modified, deleted) { yes | no}
        "subscription"          : ""

        # The ID of an existing subscription to renew
        "id"                    : int
    }
    """
    valid_query_filters = [
        "query-target",
        "target-subtree-class",
        "query-target-filter",
        "rsp-subtree",
        "rsp-subtree-class",
        "rsp-subtree-filter",
        "rsp-subtree-include",
        "order-by",
        "rsp-prop-include",
        "page-size",
        "subscription",
        "id",
    ]
    query_string = ""
    if query_filters is None or len(query_filters.keys()) == 0:
        return query_string

    # check valid query filters
    try:
        for filter_key in query_filters.keys():
            if filter_key not in valid_query_filters:
                raise KeyError(
                    (
                        "ACI APIC REST Query filter parsing error: " "Invalid Query Filter Key: {}"
                    ).format(filter_key)
                )
            if len(str(query_filters[filter_key])) == 0:
                continue
            # querystring string quotes MUST be double not single
            if isinstance(query_filters[filter_key], int):
                flt = query_filters[filter_key]
            else:
                flt = query_filters[filter_key].replace("'", '"')
            query_string = "&".join(
                (
                    query_string,
                    "{filter_key}={filter_string}".format(filter_key=filter_key, filter_string=flt),
                )
            )

    except Exception as e:
        msg = "ACI APIC REST Query filter parsing error: {}".format(str(e))
        print(msg)
        raise Exception(msg)

    # remove leading ampersand
    query_string = query_string[1:]
    return "?" + query_string
