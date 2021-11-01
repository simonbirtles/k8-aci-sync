"""
.
"""
from exceptions import CachedObjectNotFoundError

_k8_objects = []


def add_k8_object(k8_object):
    """
    .
    """
    uid = k8_object.metadata.uid
    for i, obj in enumerate(_k8_objects):
        if uid == obj.uid:
            if k8_object.metadata.resource_version == obj.resource_version:
                return
            del _k8_objects[i]
            print("\tRemoved stale K8 object with ID: {}".format(obj.uid))

    _k8_objects.append(K8Object(k8_object))
    print("\tAdded K8 object {} with UID {} to local cache".format(k8_object.kind, uid))


def del_k8_object(uid):
    """
    .
    """
    for i, obj in enumerate(_k8_objects):
        if uid == obj.uid:
            print("\tRemoved stale K8 object with ID: {}".format(obj.uid))
            del _k8_objects[i]
            return
    else:
        print("\tNo K8 object with UID {} in cache to delete.".format(uid))


def get_k8_object(uid):
    """
    Returns the cached K8 object as { 'metadata': {...}, 'status':{...}, ... }
    """
    for i, obj in enumerate(_k8_objects):
        if uid == obj.uid:
            return _k8_objects[i].obj

    raise CachedObjectNotFoundError("K8 object with UID {} not in cache.".format(uid))

class K8Object:
    """
    Objects/Kind:
        Deployment
        Pod
        Service
    """

    def __init__(self, obj):
        """ """
        self._object = obj

    @property
    def kind(self):
        return self._object.kind

    @property
    def uid(self):
        return self._object.metadata.uid

    @property
    def resource_version(self):
        return self._object.metadata.resource_version

    @property
    def obj(self):
        return self._object
