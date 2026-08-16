"""Structured execution errors shared by Runtime / Worker.

`ExecutionError` is defined in `app.connectors.base` (the lowest execution
layer) and re-exported here so Runtime code can import it from this module.
"""

from app.connectors.base import ExecutionError

__all__ = ["ExecutionError"]
