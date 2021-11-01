"""

"""
from kubernetes import client


def get_replicaset(namespace, name):
    """ """
    _core_apps = client.AppsV1Api()
    replicaset = _core_apps.list_namespaced_replica_set(
        namespace, field_selector="metadata.name={}".format(name)
    )
    rs = replicaset.items[0] if len(replicaset.items) == 1 else None
    return rs
