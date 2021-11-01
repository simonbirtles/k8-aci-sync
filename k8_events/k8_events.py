"""
"""
import traceback
from .k8_events_deployment import event_deployment
from .k8_events_pod import event_pod
from .k8_events_service import event_service

event_map = {"Deployment": event_deployment, "Service": event_service, "Pod": event_pod}


def process_k8_event(event):
    try:
        f = event_map[event["object"].kind]
        f(event)
    except Exception as e:
        print('Unhandled error occurred in K8 Events Handlers')
        print('Error: {}'.format(stre(e)))
        print(traceback.format_exc())
