"""
Utility functions for the crawler.
"""

from __future__ import annotations


BASE = "https://archiveofourown.org/works/{id}?view_full_work=true"


def get_work_url(ao3_id: int) -> str:
    """
    Return the URL of a work.

    :param ao3_id:
    :return:
    """
    return BASE.format(id=ao3_id)
