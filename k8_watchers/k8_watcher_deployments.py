"""
"""
from queue import Empty
import traceback
from threading import Thread
from kubernetes import client, watch
from kubernetes.client import exceptions


class DeploymentWatcher(Thread):
    """ """

    def __init__(self, inQ, outQ, outQLock, resource_version):
        Thread.__init__(self)
        self._inQ = inQ
        self._outQ = outQ
        self._outQLock = outQLock
        self._resource_version = resource_version

        self._core_api = client.CoreV1Api()
        self._core_apps = client.AppsV1Api()
        self._watcher = watch.Watch()

        self._log("Init DeploymentWatcher Instance")
        self._start_thread()

    def _start_thread(self):
        """
        Starts the thread up.
        """
        Thread.daemon = False  # do not terminate abruptly

        self._log("Starting DeploymentWatcher Thread.")
        self.start()

    def run(self):
        """ """
        while True:

            try:
                events = self._watcher.stream(
                    self._core_apps.list_deployment_for_all_namespaces,
                    resource_version=self._resource_version,
                    timeout_seconds=1,
                )
                for event in events:
                    self._outQLock.acquire()
                    self._outQ.put(event)
                    self._outQLock.release()
                    self._resource_version = event["object"].metadata.resource_version

                try:
                    event = self._inQ.get(block=False)
                    if event is None:
                        print("Terminated K8 DeploymentWatcher Thread.")
                        return
                except Empty as e:
                    pass

            except exceptions.ApiException as e:
                print("K8 Exception: DeploymentWatcher Error: {}".format(str(e)))

            except Exception as e:
                # dedicated thread so ensure we send any unhandled
                # errors to stdout
                print("Unhandled error in K8 DeploymentWatcher thread: {}".format(str(e)))
                print(traceback.format_exc())

    def _log(self, msg):
        print(msg)
