"""
.
"""
from k8_helpers.k8_helpers import print_event, extract_k8_annotation
from k8_helpers.k8_object import add_k8_object, del_k8_object, get_k8_object
from aci_helpers.aci_object import watch_managed_object, unwatch_managed_object
from aci_helpers.aci_object import register_managed_object_callback, update_cached_managed_object
from exceptions import ManagedObjectNotFoundError, CachedObjectNotFoundError
from aci_helpers.aci_helpers import get_l3out_epg, delete_managed_object, get_eepg_subnets


def event_deployment(event):
    """
    Kind: Deployment
    """

    try:
        annotation = extract_k8_annotation(event["object"].metadata.annotations)
    except Exception as e:
        # the object does not have a haystacknetworks.com annotation
        return

    print_event(event)
    print("\t{}".format(annotation))

    # We are dealing with .....
    print("\tTenant:     /api/mo/uni/tn-{}".format(annotation["tenant"]))
    print(
        "\tLayer3 Out: /api/mo/uni/tn-{}/out-{}/instP-{}".format(
            annotation["tenant"], annotation["l3out"], annotation["epg"]
        )
    )

    # call relevent action func
    event_type_funcs = {
        "ADDED": _add_event,
        "MODIFIED": _mod_event,
        "DELETED": _del_event,
    }
    event_type_funcs[event["type"]](event, annotation)
    return


def _add_event(event, aci_data):
    """
    ADDED (Is New & Startup Sync)
      - Create the L3Out EEPG in the Tenant...
      - Tenant/L3O must exist
      - Security Domains for tenant access mapped to K8 namespace ?
    """
    print("\tDeployment Add Event")

    # add object to app cache
    add_k8_object(event["object"])

    try:
        epg = _get_l3out_epg(aci_data)
        print("\tL3Out EPG Description:", epg["attributes"]["descr"])

    except ManagedObjectNotFoundError as e:
        # The Parent objects dont exist so we cant create this MO
        # So setup APIC subscription to watch for the parent (Tenant/L3Out) creation
        # with callback which will then create the L3O EEPG

        # Start callback func
        def create_eepg():
            try:
                obj = get_k8_object(event["object"].metadata.uid)
            except CachedObjectNotFoundError as e:
                # k8 object no longer exists in cache so
                # must have been deleted, so dont create ACI object
                return

            try:
                annotation = extract_k8_annotation(obj.metadata.annotations)
            except Exception as e:
                # the object does not have a haystacknetworks.com annotation
                return

            print(
                "\tCreating L3Out EEPG from L3Out parent created event for: {}/{}/{}".format(
                    annotation["tenant"], annotation["l3out"], annotation["epg"]
                )
            )
            epg = _get_l3out_epg(annotation)
            return

        # End callback func

        # Create subscription for parent DN (tenant/l3out) 'created' event
        # and pass callback func for APIC MO 'created' event
        parent_dn = "/uni/tn-{}/out-{}".format(aci_data["tenant"], aci_data["l3out"])
        print(
            "\tRegistering callback function for created event for parent dn: {}".format(parent_dn)
        )
        register_managed_object_callback(dn=parent_dn, action="created", callback_func=create_eepg)

    return


def _get_l3out_epg(aci_data):
    """ """
    try:
        # creates the EEPG if it does not exist
        epg = get_l3out_epg(
            aci_data["tenant"], aci_data["l3out"], aci_data["epg"], create_if_absent=True
        )

        # Add APIC watcher for EEPG DN (l3extInstP) and update the cache with MO data
        # The cache MO object MUST have a valid MO config now we have created the APIC MO
        if "aci-k8-haystack" in epg["attributes"]["annotation"]:
            try:
                # In case it exists already
                update_cached_managed_object(epg["attributes"]["dn"], {"l3extInstP": epg})
            except Exception as e:
                # if not create MO cache and subs
                watch_managed_object(epg["attributes"]["dn"])

    except ManagedObjectNotFoundError as e:
        print(
            (
                "\tThe APIC tenant: {} and L3Out: {} must already exist. " "Please create them."
            ).format(aci_data["tenant"], aci_data["l3out"])
        )
        raise

    return epg


def _mod_event(event, aci_data):
    """
    MODIFIED
      - Dont this we really care about deployment being modified ?
      - What if the annotations have been changed ? how do we get old and new?
    """
    print("\tDeployment Modified Event")
    # TODO: Deployment Modify
    print("\t**** TODO: Deployment Modify ****")


def _del_event(event, aci_data):
    """
    DELETED
      - We need to delete anything to do with this in ACI, but
        how do we identify if its been deleted and we cant get
        info on pods (ip) and service (ip)
        BUT the L3Out can be destroyed which contains all this ,
        can either mark with special aci tag/annotation or just use
        the k8 deployment annotation.
    """
    print("\tDeployment Deleted Event")

    # Stop Any Subscriptions
    eepg_dn = "/uni/tn-{}/out-{}/instP-{}".format(
        aci_data["tenant"], aci_data["l3out"], aci_data["epg"]
    )
    # TODO: delete all APIC subs with a dn path starting with EEPG Dn
    # i.e. unsubscribe... /uni/tn-TEN_K8_C1/out-L3O_K8_C1/instP-EPG_K8_APP_MCAST/extsubnet#[]
    # with haystack annotation
    unwatch_managed_object(eepg_dn)

    # Delete EEPG if managed by us, if not delete subnets where managed by us.
    try:
        eepg = get_l3out_epg(aci_data["tenant"], aci_data["l3out"], aci_data["epg"])
    except ManagedObjectNotFoundError as e:
        # eepg no longer exists in aci,
        # TODO: Subscriptions for now deleted EEPG/Subnets ?
        # Or is this dealt with when APIC sub event deleted is recieved?
        # Could just loop through subscrptions and delete any with
        # eepg dns prefix
        pass

    else:

        try:
            # get all EEPG subnets that are managed
            eepg_subnets = get_eepg_subnets(aci_data["tenant"], aci_data["l3out"], aci_data["epg"])
            subnets = eepg_subnets["children"]
            for subnet in subnets:
                if list(subnet.keys())[0] == "l3extSubnet":
                    subnet_dn = "/{}/{}".format(
                        eepg_subnets["attributes"]["dn"], subnet["l3extSubnet"]["attributes"]["rn"]
                    )
                    unwatch_managed_object(subnet_dn)
                    delete_managed_object(subnet_dn)

        except ManagedObjectNotFoundError as e:
            # the L3out no longer exists, so do nothing in ACI
            pass

        except KeyError as e:
            # no managed children (l3extSubnet) to delete, nothing to do
            pass

        # Check if annotation exists, if not dont delete
        if "aci-k8-haystack" in eepg["attributes"]["annotation"]:
            delete_managed_object(eepg_dn)

    del_k8_object(event["object"].metadata.uid)
