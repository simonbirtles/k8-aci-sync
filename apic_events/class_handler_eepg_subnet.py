"""
"""
import json
from aci_helpers.aci_object import get_cached_managed_object, update_cached_managed_object
from aci_apic.aci_apic import REST_Error, post, get

ignore_attributes = ["childAction", "dn", "modTs", "rn", "status"]


def class_handler_eepg_subnet(event):
    """
    APIC Managed Object External EPG Subnet (l3extSubnet) Event Handler

    event: APIC subscription payload raw json/dict. { 'subscriptionId': [...], 'imdata': [{...}]}

    Handled subscription 'status' type:
        - created
        - modified
        - deleted
    """
    print("Class Handler: l3extSubnet")

    event_mo = event["imdata"][0]

    # check we have a managed object cached
    try:
        cached_mo = get_cached_managed_object(event_mo["l3extSubnet"]["attributes"]["dn"])
    except Exception as e:
        # not found in cache, likely that its just a event raised
        # after a object has been unwatched but not yet expired on apic
        # ignore it
        return

    actions = {"created": _created, "modified": _modified, "deleted": _deleted}
    # both mo's are dicts like { 'l3extSubnet': { ... } }
    # call action function with cached and event mo's
    # TODO: do we want to wrap here for unhandled exceptions or leave at
    # process_apic_event with less context ?
    actions[event_mo["l3extSubnet"]["attributes"]["status"]](event_mo, cached_mo.mo)
    return


def _created(event_mo, cached_mo):
    """
    ACI APIC Managed Object created event

    event_mo:dict  - { 'l3extSubnet': { ... } }
    cached_mo:dict - { 'l3extSubnet': { ... } }

    Creation event, must mean that it did not exist whilst we had subs on it,
    may have been deleted manually, then recreated manually or by code
    """
    print("\nCreated event")
    # if the object is in the cache then we can ignore this, likely
    # from a re-creation of the object, but we will update the cache mo
    dn = cached_mo["l3extSubnet"]["attributes"]["dn"]
    event_attributes = event_mo["l3extSubnet"]["attributes"]
    # ok to use event_mo here for cache as its a new object so contains
    # all object attributes
    event_scopes = event_attributes["scope"].split(",") if len(event_attributes["scope"]) > 1 else []
    event_scopes.append("import-security")
    scope = ",".join(set(event_scopes))
    event_attributes["scope"] = scope
    update_cached_managed_object(dn, event_mo)
    return


def _modified(event_mo, cached_mo):
    """
    ACI APIC Managed Object modified event

    event_mo:dict  - { 'l3extSubnet': { ... } }
    cached_mo:dict - { 'l3extSubnet': { ... } }

    Modified
     - only care that the following are not changed:
        scope contains import-security
        name
        ip (impossible to change without delete then create)
        annotation contains 'orchestrator:aci-k8-haystack'

     - update cache with new
    """
    print("\nModified event")
    event_attributes = event_mo["l3extSubnet"]["attributes"]
    cached_attributes = cached_mo["l3extSubnet"]["attributes"]

    print(event_attributes)

    name_modified = "name" in event_attributes
    scope_modified = (
        "scope" in event_attributes and "import-security" not in event_attributes["scope"]
    )
    annotation_modified = (
        "annotation" in event_attributes
        and "orchestrator:aci-k8-haystack" not in event_attributes["annotation"]
    )

    print(scope_modified, name_modified, annotation_modified)
    print(not (scope_modified or name_modified or annotation_modified))

    if not (scope_modified or name_modified or annotation_modified):
        print("No significant change, updating cache with event object")
        dn = cached_attributes["dn"]
        try:
            data = get("/api/mo/" + dn)
        except REST_Error as e:
            print(
                (
                    "Error attempting to get updated MO for DN {} for cache, " "cache not updated"
                ).format(dn)
            )
        else:
            update_cached_managed_object(dn, data["imdata"][0])

        return

    scope = cached_attributes["scope"]
    if scope_modified:
        event_scopes = (
            event_attributes["scope"].split(",") if len(event_attributes["scope"]) > 1 else []
        )
        event_scopes.append("import-security")
        scope = ",".join(event_scopes)

    annotation = cached_attributes["annotation"]
    if annotation_modified:
        event_annotation = event_attributes["annotation"].split(",")
        event_annotation.append("orchestrator:aci-k8-haystack")
        annotation = ",".join(event_annotation)

    dn = cached_attributes["dn"]

    payload = {
        "l3extSubnet": {
            "attributes": {
                "annotation": annotation,
                "descr": "",
                "ip": cached_attributes["ip"],
                "name": cached_attributes["name"],
                "scope": scope,
            }
        }
    }

    try:
        data = post("api/mo/" + dn, payload)
    except REST_Error as e:
        raise

    print(json.dumps(data, indent=1))
    update_cached_managed_object(dn, data["imdata"][0])

    return


def _deleted(event_mo, cached_mo):
    """
    ACI APIC Managed Object deleted event

    event_mo:dict  - { 'l3extSubnet': { ... } }
    cached_mo:dict - { 'l3extSubnet': { ... } }

    Deleted
    - check object cache, if exists and we manage, recreate it.
    - update cache with new
    """
    print("\nDeleted event")
    # validate this is a managed object - we kinda now it is anyway as
    # its in the mo cache, but for now just check the annotation of the object
    # but dont act upon absence.
    event_attributes = event_mo["l3extSubnet"]["attributes"]
    cached_attributes = cached_mo["l3extSubnet"]["attributes"]

    if "aci-k8-haystack" not in cached_attributes["annotation"]:
        print("Haystack annotation NOT found in cached object {}".format(cached_attributes["dn"]))
        # TODO: remove subscription ? / maybe entire if statement can be removed.
        raise Exception("is even this a valid situation ?")

    print("Haystack annotation found in cached object {}".format(cached_attributes["dn"]))

    # At this point we should be convinced the object should be reinstated.
    # Reinstate as base default configuration
    # print(json.dumps(cached_mo, indent=2))
    dn = cached_attributes["dn"]
    payload = {
        "l3extSubnet": {
            "attributes": {
                "annotation": "orchestrator:aci-k8-haystack",
                "descr": "",
                "ip": cached_attributes["ip"],
                "name": cached_attributes["name"],
                "scope": "import-security",
            }
        }
    }
    data = post("api/mo/" + dn, payload)
