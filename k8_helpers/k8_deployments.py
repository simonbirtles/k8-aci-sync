"""
"""
from kubernetes import client


def get_all_deployments():
    """
    Get all deployments
    Returns V1DeploymentList
    """
    _core_apps = client.AppsV1Api()
    deployment = _core_apps.list_deployment_for_all_namespaces()
    # TODO: Initial Sync Needs _continue and items remaining code
    print("** Initial Sync Needs _continue and items remaining code **")
    # V1DeploymentList
    return deployment


def get_deployment(namespace, name):
    """ """
    _core_apps = client.AppsV1Api()
    deployment = _core_apps.list_deployment_for_all_namespaces(
        field_selector="metadata.namespace={},metadata.name={}".format(namespace, name)
    )
    return deployment.items[0]
