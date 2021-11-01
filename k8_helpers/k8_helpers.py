"""
.
"""
import json


def print_event(event):
    print("\n")
    try:
        print(
            "{:<8} {:<15} {:<10} {:<50} {:<50}".format(
                event["type"],
                event["object"].kind,
                event["object"].metadata.resource_version,
                event["object"].metadata.namespace,
                event["object"].metadata.name,
            )
        )
    except Exception as e:
        print(event)
        print(str(e))
        raise


def extract_k8_annotation(annotations):
    """
    Only deals with "aci.haystacknetworks.com/l3o" value,
    needs to be more generic if we use more annotations.
    """
    # Check we care about this item
    haystack_annotations = {}
    for k in annotations.keys():
        if "haystacknetworks.com" in k:
            haystack_annotations[k] = annotations[k]

    if len(haystack_annotations) == 0:
        raise Exception("No haystacknetworks annotations found")

    # print("\t{}".format(haystack_annotations))
    # validate annotation value format - only one type currently
    try:
        d = json.loads(haystack_annotations["aci.haystacknetworks.com/l3o"])
        d["tenant"]
        d["l3out"]
        d["epg"]
    except KeyError as e:
        print(
            'Did not find expected annotation in deployment, expected "aci.haystacknetworks.com/l3o"'
        )
        raise KeyError(
            'Did not find expected annotation in deployment, expected "aci.haystacknetworks.com/l3o"'
        )

    return d
