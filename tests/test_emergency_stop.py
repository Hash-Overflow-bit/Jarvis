"""
tests/test_emergency_stop.py
============================
Unit tests for emergency stop keyword triggers and active task termination.
"""

import pytest
from unittest.mock import MagicMock
from core.safety.emergency_stop import emergency_stop


def test_emergency_stop_registration():
    """Verify registration and unregistration of active subprocess handles."""
    # Start clean
    emergency_stop.active_processes.clear()

    mock_proc1 = MagicMock()
    mock_proc2 = MagicMock()

    emergency_stop.register_process(mock_proc1)
    emergency_stop.register_process(mock_proc2)
    assert len(emergency_stop.active_processes) == 2

    emergency_stop.unregister_process(mock_proc1)
    assert len(emergency_stop.active_processes) == 1
    assert mock_proc2 in emergency_stop.active_processes


def test_emergency_stop_halt():
    """Verify that calling halt_all terminates all registered processes."""
    emergency_stop.active_processes.clear()

    mock_proc1 = MagicMock()
    mock_proc2 = MagicMock()

    emergency_stop.register_process(mock_proc1)
    emergency_stop.register_process(mock_proc2)

    halted_count = emergency_stop.halt_all()
    assert halted_count == 2
    assert len(emergency_stop.active_processes) == 0

    # Verify terminate() was called on each process
    mock_proc1.terminate.assert_called_once()
    mock_proc2.terminate.assert_called_once()
