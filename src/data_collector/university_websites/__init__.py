"""
University website collectors.

Each module collects Computer Science academics from
a specific Australian university.
"""

from .usyd_collector import collect_usyd
from .unsw_collector import collect_unsw
from .uts_collector import collect_uts
from .unimelb_collector import collect_unimelb
from .macquarie_collector import collect_macquarie
from .monash_collector import collect_monash
from .rmit_collector import collect_rmit
from .uq_collector import collect_uq
from .anu_collector import collect_anu


__all__ = [
    "collect_usyd",
    "collect_unsw",
    "collect_uts",
    "collect_unimelb",
    "collect_macquarie",
    "collect_monash",
    "collect_rmit",
    "collect_uq",
    "collect_anu",
]