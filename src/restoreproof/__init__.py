"""Local restore drill evidence. Digests are not authentication."""
from .core import Limits, RestoreError, drill, plan, snapshot
from .fixture import make_fixture

__all__ = ["Limits", "RestoreError", "drill", "plan", "snapshot", "make_fixture"]
__version__ = "0.1.1"
