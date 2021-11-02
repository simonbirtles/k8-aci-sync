"""
"""
from queue import Empty
import traceback
import json
from websocket import _exceptions
from time import sleep
from queue import Queue
from threading import Thread, Lock
from .aci_apic import get_websocket


class NormalTerminationError(Exception):
    ...


class APICWatcher(Thread):
    """
    Listens for APIC Websocket Events
    """

    def __init__(self, inQ: Queue, outQ: Queue, outQLock: Lock):
        Thread.__init__(self)
        self._inQ = inQ
        # Out Q - Events from APIC are pushed in
        self._outQ = outQ
        self._outQLock = outQLock

        self._log("Init APICWatcher Instance")
        self._start_thread()

    def _start_thread(self):
        """
        Starts the thread up.
        """
        Thread.daemon = False  # do not terminate abruptly

        self._log("Starting APICWatcher Thread.")
        self.start()

    def run(self):
        """ """

        try:
            self.event_watcher()

        except NormalTerminationError as e:
            print("Terminated ACI APICWatcher Thread.")
            return

        except Exception as e:
            print("Unhandled error in APIC Subscription Watcher thread: {}".format(str(e)))
            raise

    def event_watcher(self):
        """ """
        while True:

            try:
                event = get_websocket().recv()

            except Exception as e:
                event = self._inQ.get(block=False)
                if event is None:
                    # event is none is the event a termination of the
                    # thread has been requests
                    raise NormalTerminationError()

            if not len(event):
                continue

            self._outQ.put(json.loads(event))

    def _log(self, msg):
        print(msg)
