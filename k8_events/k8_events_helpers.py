"""
'
"""
from k8_helpers.k8_object import get_k8_object
from aci_helpers.aci_helpers import create_eepg_subnet as api_create_eepg_subnet
from aci_helpers.aci_object import watch_managed_object, update_cached_managed_object
from exceptions import ManagedObjectNotFoundError, CachedObjectNotFoundError


def create_eepg_subnet(name, ip, dn_data):
    """
    Create the l3extSubnet in the l3out l3extInstP (EEPG)

    name:str - Short decrcription
    ip:str - Host IP address without mask.
    dn_data:dict - Keys: tenant, l3out, epg (names)

    Raises:
    - ManagedObjectNotFoundError: If the parent MOs do not exist
    """
    try:
        # Create the l3extSubnet in the l3out l3extInstP (EEPG)
        subnet = api_create_eepg_subnet(
            dn_data["tenant"],
            dn_data["l3out"],
            dn_data["epg"],
            ip,
            name,
        )

        # Add APIC watcher for EEPG Subnet DN (l3extSubnet) and update the cache with MO data
        # The cache MO object MUST have a valid MO config now we have created the APIC MO
        try:
            # In case it exists already
            watch_managed_object(subnet["attributes"]["dn"])
        except Exception as e:
            # if not create MO cache and subs
            update_cached_managed_object(subnet["attributes"]["dn"], {"l3extSubnet": subnet})

    except ManagedObjectNotFoundError as e:
        print(
            ("\tThe APIC tenant: {}, L3Out: {} must already exist. " "Please create them.").format(
                dn_data["tenant"], dn_data["l3out"]
            )
        )
        raise

    return subnet


def create_pod_subnet_callback(event, dn_data):
    """
    '
    """

    # Start callback func
    def create_subnet():
        try:
            obj = get_k8_object(event["object"].metadata.uid)
        except CachedObjectNotFoundError as e:
            # k8 object no longer exists in cache so
            # must have been deleted, so dont create ACI object
            return

        name = "{}::{}".format(obj.metadata.namespace, obj.metadata.name)
        # this ip is from Pod Object Path
        ip = obj.status.pod_ip

        print(
            "\tCreating l3ExtSubnet in l3out parent created event for: {}/{}/{}/{}".format(
                dn_data["tenant"], dn_data["l3out"], dn_data["epg"], ip
            )
        )

        subnet = create_eepg_subnet(name, ip, dn_data)
        return

    # End callback func

    return create_subnet


def create_service_subnet_callback(event, dn_data):
    """
    '
    """

    # Start callback func
    def create_subnet():

        try:
            obj = get_k8_object(event["object"].metadata.uid)
        except CachedObjectNotFoundError as e:
            # k8 object no longer exists in cache so
            # must have been deleted, so dont create ACI object
            return

        service_ip_list = event["object"].status.load_balancer.ingress
        service_is_load_balancer = event["object"].spec.type == "LoadBalancer"
        if not service_is_load_balancer:
            return

        # for each assigned service ip
        for service in service_ip_list:

            name = "{}::{}".format(obj.metadata.namespace, obj.metadata.name)
            print(
                "\tCreating l3ExtSubnet in l3out parent created event for: {}/{}/{}/{}".format(
                    dn_data["tenant"], dn_data["l3out"], dn_data["epg"], service.ip
                )
            )

            subnet = create_eepg_subnet(name, service.ip, dn_data)
        return

    # End callback func

    return create_subnet
