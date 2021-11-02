"""
'
"""
import _thread
from time import sleep

_terminate_flag = False
_terminate_flag_lock = _thread.allocate_lock()


def set_terminate_flag():
    global _terminate_flag
    with _terminate_flag_lock:
        _terminate_flag = True


def has_terminate_flag():
    with _terminate_flag_lock:
        return _terminate_flag


def thread_sleep_check(sleep_time, terminate_check_func):
    """ """
    check_interval = 5
    check_intervals = round(sleep_time / check_interval)
    for i in range(0, check_intervals):
        sleep(check_interval)
        if terminate_check_func():
            raise Exception("Normal Thread Termination")
