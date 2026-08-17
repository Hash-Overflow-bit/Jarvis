"""
core/safety/emergency_stop.py
==============================
Emergency stop coordinator to cancel active background subprocesses.
"""


class EmergencyStop:
    """Manages active subprocess cancellation on emergency halts."""

    def __init__(self):
        self.active_processes = set()

    def register_process(self, proc):
        """Registers a newly spawned asyncio subprocess."""
        self.active_processes.add(proc)

    def unregister_process(self, proc):
        """Unregisters a completed or terminated subprocess."""
        self.active_processes.discard(proc)

    def halt_all(self) -> int:
        """
        Kills all active subprocesses immediately.
        Returns the number of terminated processes.
        """
        count = len(self.active_processes)
        for proc in list(self.active_processes):
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            except OSError:
                pass
            except Exception:
                pass
        self.active_processes.clear()
        return count


# Global emergency stop singleton
emergency_stop = EmergencyStop()
