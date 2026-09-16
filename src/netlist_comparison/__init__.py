"""Conditional comparison of the structure retained in canonical netlists."""
from .api import compare, compare_instances
from .model import InputScope, Options

__all__ = ["compare", "compare_instances", "InputScope", "Options"]
