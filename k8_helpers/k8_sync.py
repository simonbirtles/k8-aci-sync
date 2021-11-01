"""
"""

from k8_helpers.k8_deployments import get_all_deployments
from k8_helpers.k8_pods import get_all_pods
from k8_helpers.k8_services import get_all_services

from k8_events.k8_events_deployment import event_deployment
from k8_events.k8_events_pod import event_pod
from k8_events.k8_events_service import event_service


def sync_deployments():
    """ """
    print("Syncing Deployments")
    dep_list = get_all_deployments()
    resource_version = dep_list.metadata.resource_version
    for dep in dep_list.items:
        dep.kind = "Deployment"
        event_deployment({"type": "ADDED", "object": dep})
    # print('Deployment Resource Version: ', resource_version)
    return resource_version


def sync_pods():
    """ """
    print("Syncing Pods")
    pod_list = get_all_pods()
    resource_version = pod_list.metadata.resource_version
    for pod in pod_list.items:
        pod.kind = "Pod"
        event_pod({"type": "ADDED", "object": pod})
    # print('Pods Resource Version: ', resource_version)
    return resource_version


def sync_services():
    """ """
    print("Syncing Services")
    service_list = get_all_services()
    resource_version = service_list.metadata.resource_version
    for service in service_list.items:
        service.kind = "Service"
        event_service({"type": "ADDED", "object": service})
    # print('Services Resource Version: ', resource_version)
    return resource_version
