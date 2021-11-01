"""
.
"""
from kubernetes import client

def get_all_services():
    """
    Get K8 Services
    Returns V1ServiceList
    """
    _core_api = client.CoreV1Api()
    services = _core_api.list_service_for_all_namespaces()
    # V1ServiceList
    return services
