#!/usr/local/bin/python3.9
"""
#!/usr/bin/python3
"""
from queue import Queue, Full, Empty
from threading import Thread, Lock
import _thread
import signal
from time import sleep
from kubernetes import client, watch, config as k8_config
from k8_watchers.k8_watcher_deployments import DeploymentWatcher
from k8_watchers.k8_watcher_services import ServiceWatcher
from k8_watchers.k8_watcher_pods import PodWatcher
from k8_events.k8_events import process_k8_event
from k8_helpers.k8_sync import sync_deployments, sync_pods, sync_services
from apic_events.apic_events import process_apic_event
from aci_apic.aci_apic import login as apic_login  # auto calls APIC login/fresh code
from aci_apic.aci_apic import logout as apic_logout
from aci_apic.aci_apic import get_websocket
from aci_apic.aci_subscription import APICWatcher
from aci_helpers.aci_object import refresh_subscriptions, print_subscriptions

# TODO - Verbose logging from threads for expections, wrapper etc as sometimes
# caught or hidden if not caught

# TODO: Thread Exception Wrappers


def main():
    """
    .
    """
    k8_config.load_kube_config()
    apic_login()
    _thread.start_new_thread(refresh_subscriptions, ())
    # print_subscriptions, temp only for dev
    _thread.start_new_thread(print_subscriptions, ())

    print("Running K8 Sync")
    # Returns the most recent revision number
    # we processed, so the watcher can start at
    # revision number.
    rv_deps = sync_deployments()
    rv_pods = sync_pods()
    rv_svcs = sync_services()

    print("Starting Event Watchers")
    # in_q is used to push termination event into thread
    # out_q is used to puch recieved events into the watcher thread.
    deployment_in_q = Queue()
    deployment_out_q = Queue()
    deployment_out_q_lock = Lock()
    deployment_watch = DeploymentWatcher(
        deployment_in_q, deployment_out_q, deployment_out_q_lock, rv_deps
    )

    pod_in_q = Queue()
    pod_out_q = Queue()
    pod_out_q_lock = Lock()
    pod_watch = PodWatcher(pod_in_q, pod_out_q, pod_out_q_lock, rv_pods)

    service_in_q = Queue()
    service_out_q = Queue()
    service_out_q_lock = Lock()
    service_watch = ServiceWatcher(service_in_q, service_out_q, service_out_q_lock, rv_svcs)

    apic_in_q = Queue()
    apic_out_q = Queue()
    apic_out_q_lock = Lock()
    apic_watch = APICWatcher(apic_in_q, apic_out_q, apic_out_q_lock)

    k8_event_q_list = [deployment_out_q, service_out_q, pod_out_q]

    graceful_exit = GracefulExit()
    while True:
        for k8_event_kind_q in k8_event_q_list:
            try:
                process_k8_event(k8_event_kind_q.get(block=False))
            except Empty as e:
                pass

        try:
            process_apic_event(apic_out_q.get(block=False))
        except Empty as e:
            pass

        #
        # TODO: Check Threads Still Alive
        # ...

        if graceful_exit.quit_now:
            print("\nTerminating Application")
            # TODO - bring back in after ctrl-c or exception
            # terminate all threads and join

            deployment_in_q.put(None)
            pod_in_q.put(None)
            service_in_q.put(None)
            # APIC Watcher termination - maybe look at moving to asyncio instead
            # None is queue to tell thread that whenthe websocket closes, its expected.
            apic_in_q.put(None)
            # APIC logout also triggers APIC refresh and
            # subscriptions related threads to terminate
            apic_logout()
            get_websocket().close()           
            
            deployment_watch.join()
            pod_watch.join()
            service_watch.join()
            apic_watch.join()
            return

        sleep(0.5)


class GracefulExit:
    quit_now = False

    def __init__(self):
        self.original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        signal.signal(signal.SIGINT, self.original_sigint)
        self.quit_now = True


if __name__ == "__main__":
    main()
