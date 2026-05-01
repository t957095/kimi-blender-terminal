"""
Utility functions for thread-safe Blender operations.
"""

import bpy
import threading


def run_in_main_thread(func, *args, timeout=30.0, **kwargs):
    """
    Execute a function on Blender's main thread and return its result.
    If already on the main thread, executes immediately.
    Uses bpy.app.timers to schedule execution and a threading.Event to wait.
    """
    if threading.current_thread() is threading.main_thread():
        return func(*args, **kwargs)

    result = [None]
    done = threading.Event()
    timer_registered = [False]

    def wrapper():
        try:
            result[0] = ("ok", func(*args, **kwargs))
        except Exception as e:
            result[0] = ("error", e)
        finally:
            done.set()
        return None

    try:
        bpy.app.timers.register(wrapper, first_interval=0.0)
        timer_registered[0] = True
    except Exception as e:
        raise RuntimeError(f"Failed to register timer: {e}")

    if not done.wait(timeout=timeout):
        if timer_registered[0]:
            try:
                bpy.app.timers.unregister(wrapper)
            except Exception:
                pass
        raise TimeoutError(f"Main-thread execution timed out after {timeout}s")

    status, value = result[0]
    if status == "error":
        raise value
    return value
