"""
.
"""
import traceback
from aci_helpers.aci_object import get_cached_managed_object, ManagedObject
from .class_handler_eepg import class_handler_eepg
from .class_handler_eepg_subnet import class_handler_eepg_subnet

class_event_handlers = {
    "l3extInstP": class_handler_eepg,
    "l3extSubnet": class_handler_eepg_subnet,
}


def process_apic_event(event):
    """
    Process a recieved APIC subscription event.
    event: full APIC payload sent in event as dict/json
    """
    print_event(event)

    # Standard default MO class handler for all event types
    _run_class_handler(event)

    # Specific onetime callbacks registered for an event on a MO
    _run_class_callbacks(event)

    return


def _run_class_handler(event):
    """
    '
    """
    event_mo = event["imdata"][0]
    mo_class = list(event_mo.keys())[0]

    # Get MO Class Handler
    # Run Managed Object standard class handler first
    try:
        class_handler_f = class_event_handlers[mo_class]
    except KeyError as e:
        print("Received an event for mo class {}, but no handler found.".format(mo_class))
    else:
        try:
            class_handler_f(event)
        except Exception as e:
            print("Unhandled error occured in APIC MO event handlers")
            print(traceback.format_exc())
    return


def _run_class_callbacks(event):
    """
    '
    """
    event_mo = event["imdata"][0]
    mo_class = list(event_mo.keys())[0]
    dn = event_mo[mo_class]["attributes"]["dn"]
    action = event_mo[mo_class]["attributes"]["status"]

    try:
        cached_mo = get_cached_managed_object(dn)
    except Exception as e:
        cached_mo = None

    # Run any/all one time callback functions registered
    # for this event action (status)
    try:
        if cached_mo is not None:
            cached_mo.run_callbacks(action)
            print("**** PROBLEM ***** apic_events:72")
            # PROBLEM: What do we do with the cached (e.g. parent) MO/Subscription after all this
            # has been run - need to cleanup ?

    except Exception as e:
        msg = (
            "An error occurred during an attempt to run callbacks for an APIC event. "
            "The event is {} for DN: {} with error {}".format(action, dn, str(e))
        )
        print(msg)
        print(traceback.format_exc())
    return


def print_event(event):
    # ignore_attributes = ["childAction", "modTs", "rn", "status"]
    moclass = list(event["imdata"][0].keys())[0]
    action = event["imdata"][0][moclass]["attributes"]["status"]
    dn = event["imdata"][0][moclass]["attributes"]["dn"]

    # print(event)
    print("APIC Object {} has been {}. DN:{} Attributes:".format(moclass, action, dn))
    for k, v in event["imdata"][0][moclass]["attributes"].items():
        # if k not in ignore_attributes:
        print("\t{} = {}".format(k, v))
