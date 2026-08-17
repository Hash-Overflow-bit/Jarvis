"""
core/safety/exception_handler.py
================================
Safe execution wrapper for running tools and handling unexpected failures.
"""

from typing import Callable, Any
from core.logging.audit_logger import audit_logger


async def safe_execute(
    tool_name: str,
    parameters: dict,
    execute_func: Callable[[], Any]
) -> dict:
    """
    Executes a tool function safely within a try-catch block.
    Logs any failure in the audit logger and returns a standard error dict.
    """
    try:
        # Check if executing function is a coroutine or standard callable
        import inspect
        if inspect.iscoroutinefunction(execute_func):
            result_data = await execute_func()
        else:
            result_data = execute_func()

        # Log successful completion
        audit_logger.log_action(
            tool_name=tool_name,
            parameters=parameters,
            status="APPROVED",
            details="Executed successfully",
            result="SUCCESS"
        )
        return {
            "success": True,
            "result": result_data
        }

    except PermissionError as e:
        error_msg = f"Security boundary violation: {str(e)}"
        audit_logger.log_action(
            tool_name=tool_name,
            parameters=parameters,
            status="APPROVED",
            details=error_msg,
            result="FAILED"
        )
        return {
            "success": False,
            "error": error_msg
        }

    except Exception as e:
        error_msg = f"Execution error in tool '{tool_name}': {str(e)}"
        audit_logger.log_action(
            tool_name=tool_name,
            parameters=parameters,
            status="APPROVED",
            details=error_msg,
            result="FAILED"
        )
        return {
            "success": False,
            "error": error_msg
        }
