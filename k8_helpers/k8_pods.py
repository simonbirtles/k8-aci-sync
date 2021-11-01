"""
.
"""
from kubernetes import client
from .k8_deployments import get_deployment
from .k8_replicasets import get_replicaset


def get_pod_deployment(pod):
    """
    Get the deployment associated with a pod only if 'haystacknetworks.com' annotation exists
    Returns 'object'
    """
    namespace = pod.metadata.namespace
    parent_uid = pod.metadata.owner_references[0].uid
    parent_kind = pod.metadata.owner_references[0].kind
    parent_name = pod.metadata.owner_references[0].name

    #
    # and DaemonSet
    #

    if parent_kind == "ReplicaSet":
        # get the replicaset object with uid: parent_uid or name: parent_name
        rs = get_replicaset(namespace, parent_name)
        if rs is None:
            # presumably it been deleted as this is probably a MODIFIED event.
            # TODO: Better MSG
            print("**DOES NOT EXIST - MODIFIED EVENT AFTER DEPLOY DELETE EVENT ?**")
            return None

        dep = get_deployment(namespace, rs.metadata.owner_references[0].name)

        haystack_annotations = {}
        for k in dep.metadata.annotations.keys():
            if "haystacknetworks.com" in k:
                haystack_annotations[k] = dep.metadata.annotations[k]
                return dep
        else:
            return None
    else:
        print(
            "**** Parent Kind {} unhandled **** {}:{}".format(
                parent_kind, namespace, pod.metadata.name
            )
        )


def get_all_pods():
    """
    Get All K8 Pods
    Returns V1PodList
    """
    _core_api = client.CoreV1Api()
    pods = _core_api.list_pod_for_all_namespaces()
    # print("Pod List Meta", "\n", pods.metadata, "\n")
    # V1PodList
    return pods


def get_pods(namespace, label):
    """
    Get K8 Pods By namespace and label
    """
    _core_api = client.CoreV1Api()
    pods = _core_api.list_pod_for_all_namespaces(
        field_selector="metadata.namespace={}".format(namespace), label_selector=label
    )
    return pods.items
