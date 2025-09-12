from __future__ import annotations
from pathlib import Path
import gzip, hashlib

from .config import STORE_ROOT


# Todo; I think json metadata would be a good add here


def get_work_path(ao3_id: int, ext: str) -> Path:
    """
    Generic getting function for files within the work's folder.

    :return:
    """
    m = ao3_id // 1_000_000
    k = (ao3_id // 1_000) % 1000
    return STORE_ROOT / "works" / f"{m:03d}" / f"{k:03d}" / f"{ao3_id:09d}" / f"{ao3_id:09d}.{ext}"


def work_path_html(ao3_id: int) -> Path:
    """
    Return a path to the html store for this work.

    :param ao3_id:
    :return:
    """
    ext = "html.gz"
    return get_work_path(ao3_id, ext)


def write_html_gz(ao3_id: int, html: str) -> tuple[int, str]:
    """
    Write the given html out to storage.

    :param ao3_id:
    :param html:
    :return:
    """
    p = work_path_html(ao3_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = html.encode("utf-8", errors="replace")

    with gzip.open(p, "wb", compresslevel=6) as f:
        f.write(data)

    sha = hashlib.sha256(data).hexdigest()
    return len(data), sha
