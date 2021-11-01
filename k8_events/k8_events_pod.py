"""
.
"""
from logging import exception
from k8_helpers.k8_pods import get_pod_deployment
from k8_helpers.k8_helpers import print_event, extract_k8_annotation
from k8_helpers.k8_object import add_k8_object, del_k8_object, get_k8_object
from aci_helpers.aci_object import watch_managed_object, unwatch_managed_object
from aci_helpers.aci_object import register_managed_object_callback, update_cached_managed_object
from exceptions import CachedObjectNotFoundError, ManagedObjectNotFoundError
from aci_helpers.aci_helpers import delete_eepg_subnet
from k8_events.k8_events_helpers import create_eepg_subnet as _create_eepg_subnet
from k8_events.k8_events_helpers import create_pod_subnet_callback


def event_pod(event):
    """
    Kind: Pod
    """
    print_event(event)
    # Gets the deployment associated with a pod only
    # if aci.haystack.com annotation exists
    deployment = get_pod_deployment(event["object"])
    if deployment is None:
        return

    # call relevent action func
    event_type_funcs = {
        "ADDED": _add_event,
        "MODIFIED": _mod_event,
        "DELETED": _del_event,
    }
    event_type_funcs[event["type"]](event, deployment)
    return


def _add_event(event, deployment):
    """
    ADDED (Is New & Startup Sync)
        - Add pod IP to EEPG subnets, but do we need a flag to enable/disable this
        - If we also populate a given PBR redirect policy, we need to adjust that too
        - uni/tn-{}/svcCont/svcRedirectPol-{--pbr--pol--name}
    """
    print("\tPod Added Event")
    print(
        "\t",
        event["object"].status.pod_ip,
        event["object"].metadata.namespace,
        event["object"].metadata.name,
    )

    # Add Pod to k8 cache
    add_k8_object(event["object"])

    try:
        dn_data = extract_k8_annotation(deployment.metadata.annotations)
    except Exception as e:
        # the object does not have a haystacknetworks.com annotation
        return

    name = "{}::{}".format(event["object"].metadata.namespace, event["object"].metadata.name)
    ip = event["object"].status.pod_ip

    # Add Pod IP as EEPG l3extSubnet if not exist
    if ip is not None:
        try:
            subnet = _create_eepg_subnet(name, ip, dn_data)
            print("\tL3Out EPG Subnet IP:", subnet["attributes"]["ip"])

        except ManagedObjectNotFoundError as e:
            # The Parent objects dont exist so we cant create this MO
            # So setup APIC subscription to watch for the parent EEPG (l3extInstP) creation
            # with callback which will then create the l3extSubnet

            cb_func = create_pod_subnet_callback(event, dn_data)

            # Create subscription for parent DN (tenant/l3out) 'created' event
            # and pass callback func for APIC MO 'created' event
            parent_dn = "/uni/tn-{}/out-{}/instP-{}".format(
                dn_data["tenant"], dn_data["l3out"], dn_data["epg"]
            )
            print(
                "\tRegistering callback function for created event for parent dn: {}".format(
                    parent_dn
                )
            )
            register_managed_object_callback(dn=parent_dn, action="created", callback_func=cb_func)
    return


def _mod_event(event, deployment):
    """
    MODIFIED
        - As above, update the EEPG Subnets if we are adding POD IPs
        and/or modify PBR policy
    """
    print("\tPod Modified Event")

    # Get Last Object From Cache
    uid = event["object"].metadata.uid
    try:
        last_obj = get_k8_object(uid)
    except CachedObjectNotFoundError as e:
        # we have not had an add for this so ignore it
        print("\tPod Modified Event - {}".format(str(e)))
        return

    try:
        dn_data = extract_k8_annotation(deployment.metadata.annotations)
    except Exception as e:
        # the object does not have a haystacknetworks.com annotation
        return

    #
    # Compare important data for updates, currently only PodIP
    # if add more, move to seperate code
    #

    # Check IP Assigned To Pod
    if event["object"].status.pod_ip != last_obj.status.pod_ip:

        if last_obj.status.pod_ip is not None:
            # Remove ACI Subnet
            delete_eepg_subnet(
                dn_data["tenant"], dn_data["l3out"], dn_data["epg"], last_obj.status.pod_ip
            )
            urlpath = "/uni/tn-{}/out-{}/instP-{}/extsubnet-[{}/32]".format(
                dn_data["tenant"], dn_data["l3out"], dn_data["epg"], last_obj.status.pod_ip
            )
            unwatch_managed_object(urlpath)

        if event["object"].status.pod_ip is not None:

            name = "{}::{}".format(event["object"].metadata.namespace, event["object"].metadata.name)
            try:
                subnet = _create_eepg_subnet(name, event["object"].status.pod_ip, dn_data)
                print("\tL3Out EPG Subnet IP:", subnet["attributes"]["ip"])

            except ManagedObjectNotFoundError as e:
                # The Parent objects dont exist so we cant create this MO
                # So setup APIC subscription to watch for the parent EEPG (l3extInstP) creation
                # with callback which will then create the l3extSubnet

                cb_func = create_pod_subnet_callback(event, dn_data)

                # Create subscription for parent DN (tenant/l3out) 'created' event
                # and pass callback func for APIC MO 'created' event
                parent_dn = "/uni/tn-{}/out-{}/instP-{}".format(
                    dn_data["tenant"], dn_data["l3out"], dn_data["epg"]
                )
                print(
                    "\tRegistering callback function for created event for parent dn: {}".format(
                        parent_dn
                    )
                )
                register_managed_object_callback(
                    dn=parent_dn, action="created", callback_func=cb_func
                )

    # update cache
    add_k8_object(event["object"])

    return


def _del_event(event, deployment):
    """
    DELETED
        - As above, remove IP from EEPG subnets
        and/or modify PBR policy
    """
    print("\tPod Deleted Event")

    uid = event["object"].metadata.uid
    try:
        last_obj = get_k8_object(uid)
    except CachedObjectNotFoundError as e:
        # we have not had an add for this so ignore it
        print("\tPod Deleted Event - {}".format(str(e)))
        return

    try:
        dn_data = extract_k8_annotation(deployment.metadata.annotations)
    except Exception as e:
        # the object does not have a haystacknetworks.com annotation
        return

    if last_obj.status.pod_ip is not None:
        delete_eepg_subnet(
            dn_data["tenant"], dn_data["l3out"], dn_data["epg"], last_obj.status.pod_ip
        )
        # Remove APIC Subscription for this Subnet
        urlpath = "/uni/tn-{}/out-{}/instP-{}/extsubnet-[{}/32]".format(
            dn_data["tenant"], dn_data["l3out"], dn_data["epg"], last_obj.status.pod_ip
        )
        unwatch_managed_object(urlpath)

    # update cache
    del_k8_object(uid)
