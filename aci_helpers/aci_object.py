"""
"""
from time import sleep
import traceback
from aci_apic.aci_apic import REST_Error, get, has_terminate_flag
from common.app_helpers import thread_sleep_check, has_terminate_flag
from typing import List


class ManagedObject:
    """ """

    def __init__(self, *, dn, mo=None, sub_id=None):
        """
        dn:str is the DN like '/uni/tn-TEN_K8/...'
        mo:dict is the dict like { "l3extSubnet": { ...}  }
        sub_id:int is the APIC subscription ID like 9298883939
        """
        self._dn = dn if dn.startswith("/") else ("/" + dn)
        self._sub_id = sub_id
        self._mo = mo
        self._callbacks = {"created": [], "modified": [], "deleted": []}

    @property
    def dn(self):
        """
        The APIC Managed Object DN as '/uni/...'
        """
        return self._dn

    @property
    def mo(self):
        """
        Returns the APIC managed object.
        Only root key is class name.
        """
        return self._mo

    @mo.setter
    def mo(self, mo):
        """
        mo should be in form { 'class-name': { ... } }
        """
        self._mo = mo

    @property
    def subscription_id(self):
        """
        Returns the APIC subscription ID for this managed object DN
        """
        return self._sub_id

    @subscription_id.setter
    def subscription_id(self, id):
        self._sub_id = id

    def has_subscription(self):
        return self._sub_id is not None

    def has_mo(self):
        return self._mo is not None

    def register_callback(self, action, f):
        """
        Registers a callback for the next event action recieved.
        A callback is only called once, it is deleted once its been called.

        action:str One of 'created','modified','deleted'
        f:func A function to be called with no params.

        """
        assert action in ["created", "modified", "deleted"]
        self._callbacks[action].append(f)

    def run_callbacks(self, action):
        """
        Runs the callbacks for the given action.
        Each callback will be run and deleted from the action list.
        Callbacks are only run once.

        action:str One of 'created','modified','deleted'
        """
        assert action in ["created", "modified", "deleted"]
        for _ in range(len(self._callbacks[action])):
            try:
                print("\nRunning callback for {} : {}".format(action, self.dn))
                func = self._callbacks[action].pop(0)
                func()
            except Exception as e:
                print("An error occurred during a callback func execution: {}" / format(str(e)))
                print(traceback.format_exc())
                # continue processing all other callbacks
        return


_managed_objects: List[ManagedObject]
_managed_objects = []


def watch_managed_object(dn):
    """
    Creates a Managed Object cache entry and creates an APIC subscription for the
    DN.

    dn:str '/uni/tn-TEN_K8/...'
    """
    print("\tWatching managed object: {}".format(dn))
    _dn = dn if dn.startswith("/") else ("/" + dn)
    global _managed_objects
    for o in _managed_objects:
        if o.dn == _dn:
            print(
                "DN: {} already being watched with subscription ID: {}".format(
                    _dn, o.subscription_id
                )
            )
            return

    data = subscribe(_dn)

    # Can be empty data if subscribing to an object that doesnt exist yet
    mo = data["imdata"][0] if len(data["imdata"]) > 0 else None

    # TODO: Lock Required
    _managed_objects.append(ManagedObject(dn=_dn, mo=mo, sub_id=data["subscriptionId"]))


def unwatch_managed_object(dn):
    """
    Deletes the ManagedObject class instance (application instance not APIC) \

    dn:str '/uni/tn-TEN_K8/...'
    """
    _dn = dn if dn.startswith("/") else ("/" + dn)
    for i, mo in enumerate(_managed_objects):
        if mo.dn == _dn:
            # TODO: Lock Required
            del _managed_objects[i]
            print("Removed APIC change subscription for DN: {}".format(_dn))
            return
    print("Did not find an active subscription for DN: {}".format(_dn))


def get_cached_managed_object(dn) -> ManagedObject:
    """
    dn: /uni/tn-TEN_K8/...
    """
    _dn = dn if dn.startswith("/") else ("/" + dn)
    for mo in _managed_objects:
        if mo.dn == _dn:
            return mo
    raise Exception("MO with DN {} not in cache.".format(dn))


def update_cached_managed_object(dn, mo):
    """
    Update the Managed Object instance config params\\
    for the given DN if the DN is found in the MO cache.

    dn:str  /uni/tn-TEN_K8/...  \\
    mo:dict  { 'class-name': { ... } }

    Raises:
        Exception if DN not found in cache
    """
    print("\tUpdating managed object: {}".format(dn))
    _dn = dn if dn.startswith("/") else ("/" + dn)
    for _mo in _managed_objects:
        if _mo.dn == _dn:
            _mo.mo = mo
            return
    raise Exception("MO with DN {} not in cache.".format(dn))


def register_managed_object_callback(dn, action, callback_func):
    """ 
    Registers a callback function to be run when a given action occurs
    on a given DN

    dn:str /uni/tn-TEN_K8/... \\
    action:str one of 'created', 'modified', 'deleted' \\
    callback_func:func A function to run when event {action} on given DN is triggered    
    """
    _dn = dn if dn.startswith("/") else ("/" + dn)
    for mo in _managed_objects:
        if mo.dn == _dn:
            mo.register_callback(action, callback_func)
            # TODO: should we check there is a valid subscription ID/running
            return
    else:
        # A ManagedObject class does not exist for the given dn.
        # 1. We need to create a class instance
        # 2. Register callback function
        # 3. Register a subscription with the APIC
        watch_managed_object(dn)
        mo = get_cached_managed_object(dn)
        mo.register_callback(action, callback_func)

    return


def subscribe(dn, options=""):
    """
    APIC Subscription to a DN \
        
    dn: /uni/tn-TEN_K8/...
    """
    _dn = dn if dn.startswith("/") else ("/" + dn)
    dn = "/api/mo{}".format(_dn)
    query_filters = {"subscription": "yes"}
    try:
        data = get(urlpath=dn, query_filters=query_filters)
    except REST_Error as e:
        msg = "APIC subscribe request failed due to {}".format(e.content)
        print(msg)
        # if e.code == 406:
        #     login()
        #     return
        # TODO: manage this better
        raise Exception(msg)

    else:
        print(
            "\tAPIC subscription successful for ID: {} with DN: {}".format(
                data["subscriptionId"], dn
            )
        )

    return data


def refresh_subscriptions():
    """
    Dedicated Thread (from login())
    """
    while True:

        try:
            thread_sleep_check(sleep_time=30, terminate_check_func=has_terminate_flag)
        except Exception as e:
            print("Terminated refresh_subscriptions thread: {}".format(str(e)))
            return

        try:

            for mo in _managed_objects:
                dn = "api/subscriptionRefresh"
                query_filters = {"id": mo.subscription_id}
                try:
                    data = get(urlpath=dn, query_filters=query_filters)
                except REST_Error as e:
                    if e.code == 400:
                        # Subscription refresh timeout
                        renew_subscriptions()
                        continue
                    print(
                        "APIC subscription refresh failed for ID: {} : {} due to {} - {}".format(
                            mo.subscription_id, mo.dn, e.code, e.content
                        )
                    )
                    continue
                # else:
                #     print(
                #         "APIC subscription refresh successful for ID: {} : DN: {}".format(
                #             mo.subscription_id, mo.dn
                #         )
                #     )
        except Exception as e:
            # dedicated thread so ensure we send any unhandled
            # errors to stdout
            print("Unhandled error in refresh_subscriptions thread: {}".format(str(e)))
            print(traceback.format_exc())


def renew_subscriptions():
    """
    Called by refresh_subscriptions only after a 400 returned
    """
    for mo in _managed_objects:

        dn = "api/mo/{}".format(mo.dn)
        params = "subscription=yes"

        try:
            data = get(dn, params)
        except Exception as e:
            print("Renewal of APIC subscription {} failed".format(mo.dn))
        else:
            # TODO: Lock Required
            mo.subscription_id = data["subscriptionId"]
            print(
                "APIC subscription renewal successful for ID: {} with DN: {}".format(
                    mo.subscription_id, mo.dn
                )
            )

    return


def print_subscriptions():
    """
    Dedicated thread (temp debug only)
    """
    while True:

        try:
            thread_sleep_check(sleep_time=15, terminate_check_func=has_terminate_flag)
        except Exception as e:
            print("Terminated print_subscriptions thread: {}".format(str(e)))
            return

        try:
            print("Subscription List")
            print("=" * 190)
            for mo in _managed_objects:
                if mo.has_subscription():
                    print(
                        "Sub ID: {:<8} DN: {:<100} MO: {:<8} Callback Count: Created:{} Modified:{} Deleted:{}".format(
                            mo.subscription_id,
                            mo.dn,
                            bool(mo.has_mo()),
                            len(mo._callbacks["created"]),
                            len(mo._callbacks["modified"]),
                            len(mo._callbacks["deleted"]),
                        )
                    )
            print("=" * 190)
        except Exception as e:
            # dedicated thread so ensure we send any unhandled
            # errors to stdout
            print("Unhandled error in print_subscriptions thread: {}".format(str(e)))
            print(traceback.format_exc())
