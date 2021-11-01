"""
"""
import traceback
import json
from time import sleep
from queue import Queue
from threading import Thread, Lock
from .aci_apic import get_websocket


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
        while True:
            try:
                event = get_websocket().recv()
                sleep(1)

            except Exception as e:
                # dedicated thread so ensure we send any unhandled
                # errors to stdout
                print("Unhandled error in ACI APICWatcher thread: {}".format(str(e)))
                print(traceback.format_exc())

            if not len(event):
                continue
            self._outQ.put(json.loads(event))

    def _log(self, msg):
        print(msg)
