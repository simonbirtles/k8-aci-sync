"""
K8 Service Event Handlers

TODO: Currently only managing ingress IP and not hostname
"""
from k8_helpers.k8_pods import get_pods, get_pod_deployment
from k8_helpers.k8_helpers import print_event, extract_k8_annotation
from k8_helpers.k8_object import add_k8_object, del_k8_object, get_k8_object
from aci_helpers.aci_object import watch_managed_object, unwatch_managed_object
from aci_helpers.aci_object import register_managed_object_callback
from aci_helpers.aci_helpers import create_eepg_subnet, delete_eepg_subnet
from k8_events.k8_events_helpers import create_eepg_subnet as _create_eepg_subnet
from k8_events.k8_events_helpers import create_service_subnet_callback
from exceptions import CachedObjectNotFoundError, ManagedObjectNotFoundError


def event_service(event):
    """
    Kind: Service
    """
    print_event(event)

    # A service is bound to pods via 'selectors: e.g. app=mcast-app, ...
    selector_dict = event["object"].spec.selector
    if selector_dict is None:
        return
    # create dict of selector k:v's
    selector_list = ["{}={}".format(key, val) for key, val in selector_dict.items()]
    selector_str = ",".join(selector_list)

    items = get_pods(event["object"].metadata.namespace, selector_str)
    deployments = []
    for pod in items:
        deployment = get_pod_deployment(pod)
        if deployment is not None:
            # save pods that are part of a deployment that
            # has the 'haystacknetworks.com' annotation
            deployments.append(deployment)
            # print_event(event)
            # print("\t Pod:        {:<20} {:<50}".format(pod.metadata.namespace, pod.metadata.name))
            # print(
            #     "\t Deployment: {:<20} {:<50}".format(
            #         deployment.metadata.namespace, deployment.metadata.name
            #     )
            # )

    dep_dn_data = []
    for dep in deployments:
        try:
            dn_data = extract_k8_annotation(deployment.metadata.annotations)
            if dn_data not in dep_dn_data:
                dep_dn_data.append(dn_data)
        except Exception as e:
            # haystacknetworks.com annotation does not exost for this deloyment
            # so ignore this deployment
            pass

    if len(dep_dn_data) == 0:
        # no managed deployments found
        return

    # call relevent action func
    event_type_funcs = {
        "ADDED": _add_event,
        "MODIFIED": _mod_event,
        "DELETED": _del_event,
    }
    event_type_funcs[event["type"]](event, dep_dn_data)
    return


def _add_event(event, dep_dn_data):
    """
    ADDED (Is New & Startup Sync)
    Need to get the LB IP and add to the EEPG Subnets
    """
    print("\tService Added Event")

    # service_ip = event["object"].status.load_balancer.ingress[0].ip
    # TODO: Do we need/want to deal with other types?
    service_is_load_balancer = event["object"].spec.type == "LoadBalancer"
    service_ip_list = event["object"].status.load_balancer.ingress

    # Add Pod IP to EEPG Subnets (l3extSubnet) if not exist
    if service_ip_list is not None and len(service_ip_list) > 0 and service_is_load_balancer:
        # as a service can point to many pods and
        # pods point to deployments, we need to make
        # sure we cover situations where we have multiple
        # end deployments in scope

        # For each deployment (tenant|l3out|eepg)
        for dn_data in dep_dn_data:

            # for each assigned service ip
            for service in service_ip_list:

                name = "{}::{}".format(
                    event["object"].metadata.namespace, event["object"].metadata.name
                )

                try:
                    subnet = _create_eepg_subnet(name, service.ip, dn_data)
                    print("\tL3Out EPG Subnet IP:", subnet["attributes"]["ip"])

                except ManagedObjectNotFoundError as e:
                    # The Parent objects dont exist so we cant create this MO
                    # So setup APIC subscription to watch for the parent EEPG (l3extInstP) creation
                    # with callback which will then create the l3extSubnet

                    cb_func = create_service_subnet_callback(event, dn_data)

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

    # Add Pod to k8 cache
    add_k8_object(event["object"])


def _mod_event(event, dep_dn_data):
    """
    MODIFIED
    Need to get and check the LB IP and add/modify in the EEPG Subnets
    """
    print("\tService Modified Event")

    uid = event["object"].metadata.uid
    try:
        last_obj = get_k8_object(uid)
    except CachedObjectNotFoundError as e:
        # we have not had an add for this so ignore it
        return

    new_service_is_load_balancer = event["object"].spec.type == "LoadBalancer"
    # old_service_is_load_balancer = last_obj.spec.type == "LoadBalancer"

    new_ingress = (
        []
        if event["object"].status.load_balancer.ingress is None
        else event["object"].status.load_balancer.ingress
    )
    old_ingress = (
        []
        if last_obj.status.load_balancer.ingress is None
        else last_obj.status.load_balancer.ingress
    )
    new_service_ip_list = [ingress.ip for ingress in new_ingress]
    old_service_ip_list = [ingress.ip for ingress in old_ingress]

    def remove_ips(ips_to_remove):
        nonlocal dep_dn_data

        if len(ips_to_remove) == 0:
            return
        # as a service can point to many pods and
        # pods point to deployments, we need to make
        # sure we cover situations where we have multiple
        # end deployments in scope
        for dn_data in dep_dn_data:
            # For each deployment (tenant|l3out|eepg)
            for service_ip in ips_to_remove:
                delete_eepg_subnet(dn_data["tenant"], dn_data["l3out"], dn_data["epg"], service_ip)

                # Remove APIC Subscription for this Subnet
                urlpath = "/uni/tn-{}/out-{}/instP-{}/extsubnet-[{}/32]".format(
                    dn_data["tenant"], dn_data["l3out"], dn_data["epg"], service_ip
                )
                unwatch_managed_object(urlpath)

    def add_ips(ips_to_add):
        nonlocal dep_dn_data

        if len(ips_to_add) == 0:
            return
        # For each deployment (tenant|l3out|eepg)
        for dn_data in dep_dn_data:
            # for each assigned service ip
            for service_ip in ips_to_add:
                name = "{}::{}".format(
                    event["object"].metadata.namespace, event["object"].metadata.name
                )
                create_eepg_subnet(
                    dn_data["tenant"], dn_data["l3out"], dn_data["epg"], service_ip, name
                )

                # Add APIC watcher for EEPG Subnet DN (l3extSubnet)
                urlpath = "/uni/tn-{}/out-{}/instP-{}/extsubnet-[{}/32]".format(
                    dn_data["tenant"], dn_data["l3out"], dn_data["epg"], service_ip
                )
                watch_managed_object(urlpath)

    # Remove subnet if either
    # - the service is not LoadBalancer
    # - the LoadBalancer IP is empty
    if not new_service_is_load_balancer or len(new_service_ip_list) == 0:
        remove_ips(old_service_ip_list)
        # Update Pod to k8 cache
        add_k8_object(event["object"])
        return

    # Add/Update subnet if either
    if (
        new_service_is_load_balancer
        and new_service_ip_list is not None
        and len(new_service_ip_list) > 0
    ):

        match = list(set(new_service_ip_list) & set(old_service_ip_list))
        if len(match) == len(new_service_ip_list):
            # no change
            return

        # Remove Old
        ips_to_remove = list(set(old_service_ip_list) - set(match))
        remove_ips(ips_to_remove)

        # Add New
        ips_to_add = list(set(new_service_ip_list) - set(match))
        add_ips(ips_to_add)

        # Update Pod to k8 cache
        add_k8_object(event["object"])
        return


def _del_event(event, dep_dn_data):
    """
    DELETED
    Remove the IP(s) from the EEPG subnets
    """
    print("\tService Deleted Event")

    uid = event["object"].metadata.uid
    try:
        last_obj = get_k8_object(uid)
    except CachedObjectNotFoundError as e:
        # we have not had an add for this so ignore it
        return

    service_is_load_balancer = last_obj.spec.type == "LoadBalancer"
    ips_to_remove = (
        []
        if last_obj.status.load_balancer.ingress is None
        else last_obj.status.load_balancer.ingress
    )

    # Add Pod IP to EEPG Subnets (l3extSubnet) if not exist
    if len(ips_to_remove) > 0 and service_is_load_balancer:
        # as a service can point to many pods and
        # pods point to deployments, we need to make
        # sure we cover situations where we have multiple
        # end deployments in scope
        for dn_data in dep_dn_data:
            # For each deployment (tenant|l3out|eepg)
            for service in ips_to_remove:
                delete_eepg_subnet(dn_data["tenant"], dn_data["l3out"], dn_data["epg"], service.ip)

                # Remove APIC Subscription for this Subnet
                urlpath = "/uni/tn-{}/out-{}/instP-{}/extsubnet-[{}/32]".format(
                    dn_data["tenant"], dn_data["l3out"], dn_data["epg"], service.ip
                )
                unwatch_managed_object(urlpath)

    # Add Pod to k8 cache
    del_k8_object(uid)
