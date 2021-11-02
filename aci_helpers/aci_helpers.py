"""
"""
import re
from aci_apic.aci_apic import REST_Error, get, post, delete
from exceptions import ManagedObjectNotFoundError


def get_tenant(name):
    """
    Returns the fvTenant MO { 'attributes: {...}}

    name:str The name of the tenant

    Raises:
    - ManagedObjectNotFoundError
    """
    data = get("/api/mo/uni/tn-{}".format(name))

    if data["totalCount"] == "1":
        return data["imdata"][0]["fvTenant"]
    else:
        raise ManagedObjectNotFoundError("Tenant {} does not exist".format(name))


def get_l3out_epg(tenant_name, l3o_name, epg_name, create_if_absent=False):
    """
    Return EEPG attributes.
    If the EEPG does not exist, create it and return attributes.
    """
    data = get("/api/mo/uni/tn-{}/out-{}/instP-{}".format(tenant_name, l3o_name, epg_name))

    if data["totalCount"] == "1":
        # L3Out / EEPG Exists
        return data["imdata"][0]["l3extInstP"]
    else:
        # Does the Tenant/L3Out Exist ?
        data = get("/api/mo/uni/tn-{}/out-{}".format(tenant_name, l3o_name))
        if data["totalCount"] == "0":
            # L3Out (or tenant) does not exist
            raise ManagedObjectNotFoundError(
                "Tenant {} Layer3 Out {} does not exist".format(tenant_name, l3o_name)
            )
        else:
            if create_if_absent:
                print("Trying to create absent EEPG - L3Out: {} EPG:{}".format(l3o_name, epg_name))
                return create_l3out_epg(tenant_name, l3o_name, epg_name)
            else:
                raise ManagedObjectNotFoundError(
                    (
                        "Tenant {} Layer3 Out {} EPG {} does not exist" " and create_if_absent=False"
                    ).format(tenant_name, l3o_name, epg_name)
                )


def get_eepg(tenant, l3out, eepg, subnet):
    """ """
    urlpath = "/api/mo/uni/tn-{}/out-{}/instP-{}/extsubnet-[{}]".format(tenant, l3out, eepg, subnet)
    data = get(urlpath)
    if data["totalCount"] == "1":
        # L3Out / EEPG Exists
        return data["imdata"][0]["l3extSubnet"]

    raise ManagedObjectNotFoundError("MO {} not found.")


def get_eepg_subnets(tenant, l3out, eepg, managed_only=True):
    """
    Returns a l3extInstP (L3Out EEPG) object from the APIC including
    any children of type l3extSubnet (L3Out EEPG Subnets).

    tenant:str - The fvTenant name
    l3out:str - The l3out name
    eepg:str - The l3extInstP name
    managed_only:bool - Searches only for l3extSubnet with haystack annotation

    Raises:
    - ManagedObjectNotFoundError

    Returns:dict - l3extInstP as { 'attributes': { ... }, 'children': { 'l3extSubnet': { ... }, ...  } }
    """
    params = {"rsp-subtree": "children", "rsp-subtree-class": "l3extSubnet"}
    if managed_only:
        params["rsp-subtree-filter"] = 'wcard(l3extSubnet.annotation, "aci-k8-haystack")'

    urlpath = "/api/mo/uni/tn-{}/out-{}/instP-{}".format(tenant, l3out, eepg)
    data = get(urlpath=urlpath, query_filters=params)
    if data["totalCount"] == "1":
        # L3Out / EEPG Exists
        return data["imdata"][0]["l3extInstP"]

    raise ManagedObjectNotFoundError("MO {} not found.")


def get_parent_from_dn(dn):
    """
    Returns the parent DN string from a given a DN string

    dn:str /api/mo/uni/tn-TEN_K8_C1/out-L3O_K8_C1/instP-EPG_K8_APP_MCAST1/extsubnet-[172.27.111.253/32]
    returns:str /api/mo/uni/tn-TEN_K8_C1/out-L3O_K8_C1/instP-EPG_K8_APP_MCAST1/
    """
    re_exp = r"^(.*)\/(?![^[]*\])"  # without the trailing /
    # re_exp  = r"(.*\/)(?![^[]*\])" # with the trailing /
    _dn = dn if not dn.endswith("/") else dn[:-1]
    res = re.match(re_exp, _dn)
    if res is not None and len(res.groups()) > 0:
        return res.groups()[0]
    else:
        raise Exception("DN string is an invalid format or DN has no parent, {}".format(_dn))


def create_l3out_epg(tenant_name, l3o_name, epg_name):
    """
    '
    """
    urlpath = "/api/mo/uni/tn-{}/out-{}".format(tenant_name, l3o_name, epg_name)
    payload = {
        "l3extInstP": {
            "attributes": {"name": epg_name, "annotation": "orchestrator:aci-k8-haystack"}
        }
    }

    data = post(urlpath, payload)

    print("Created EEPG {} for L3Out {} in Tenant {}".format(epg_name, l3o_name, tenant_name))

    # TODO: tidy up error handling if totalCount==0 (unlikely senario)
    return data["imdata"][0]["l3extInstP"]


def create_eepg_subnet(tenant, l3out, eepg, host_ip, name):
    """
    Create APIC l3extSubnet for L3Out (l3out)
    EEPG (l3extInstP) as a host (/32)

    tenant:str name of tenant (must exist)
    l3out:str name of l3out (must exist)
    eepg:str name of l3out (l3out) eepg (l3extInstP)
    host_ip:str IP address of the subnet to add as host (x.x.x.x)
    name:str short descr of the IP address purpose

    Returns the l3extSubnet MO configuration. { 'attributes': {...} }

    If the EEPG already exists, returns the EEPG MO configuration.

    Raises
    - ManagedObjectNotFoundError if the parent MO's do not exist (fvTenant, l3out, l3extInstP)
    """

    try:
        # if already exists, return managed object
        mo = get_eepg(tenant, l3out, eepg, "{}/32".format(host_ip))
    except ManagedObjectNotFoundError:
        # Managed Object does not already exist.
        pass
    else:
        # Already exists, return MO config.
        return mo

    print(
        "Creating APIC L3Out EEPG for {}|{}|{} with IP: {}, {}".format(
            tenant, l3out, eepg, host_ip, name
        )
    )

    # change to regex for /1-32, 32 default if missing
    ip = host_ip if host_ip.endswith("/32") else "{}/32".format(host_ip)
    ip_name = name[:63] if name is not None else ""
    payload = {
        "l3extSubnet": {
            "attributes": {
                "annotation": "orchestrator:aci-k8-haystack",
                "scope": "import-security",
                "ip": ip,
                "name": ip_name,
            }
        }
    }

    urlpath = "/api/mo/uni/tn-{}/out-{}/instP-{}/".format(tenant, l3out, eepg)

    try:
        mo = post(urlpath, payload)
    except REST_Error as e:
        if e.code == 400:
            # fvTenant, l3out and/or l3extInstP (parents) are absent.
            raise ManagedObjectNotFoundError("DN {} not found, parents absent?".format(urlpath))

    # created, return MO config
    return mo["imdata"][0]["l3extSubnet"]


def delete_managed_object(dn):
    """ """
    delete(dn)


def delete_eepg_subnet(tenant, l3out, eepg, host_ip):
    """
    Deletes the l3extSubnet Managed Object from the APIC.

    tenant:str - The fvTenant name
    l3out:str - The l3out name
    eepg:str - The l3extInstP name
    host_ip:str - The host address to delete (excluding mask, /32 is used internally)
    """
    urlpath = "/uni/tn-{}/out-{}/instP-{}/extsubnet-[{}/32]".format(tenant, l3out, eepg, host_ip)
    print("APIC Deleting Subnet: {}".format(urlpath))
    mo = delete(urlpath)
