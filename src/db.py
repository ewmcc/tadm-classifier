"""
db.py - Thin abstraction over pyodbc for reading Microsoft Access MDB files.

Provides a context manager (mdb_connection) that handles driver string
construction and connection lifecycle, and a read_table helper that
returns a pandas DataFrame for any named table."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pandas as pd
import pyodbc

_ACCESS_DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"


@contextmanager
def mdb_connection(mdb_path: str | Path) -> Generator[pyodbc.Connection, None, None]:
    """Context manager that opens a pyodbc connection to an Access MDB file.

    Usage::

        with mdb_connection("path/to/file.mdb") as conn:
            df = read_table(conn, "TadmCurve")

    Parameters
    ----------
    mdb_path:
        Absolute or relative path to the ``.mdb`` / ``.accdb`` file.

    Yields
    ------
    pyodbc.Connection
        An open connection that is automatically closed on exit.
    """
    mdb_path = Path(mdb_path).resolve()
    if not mdb_path.exists():
        raise FileNotFoundError(f"MDB file not found: {mdb_path}")

    conn_str = f"DRIVER={_ACCESS_DRIVER};DBQ={mdb_path};"
    conn = pyodbc.connect(conn_str)
    try:
        yield conn
    finally:
        conn.close()


def read_table(conn: pyodbc.Connection, table_name: str) -> pd.DataFrame:
    """Read an entire table from an open MDB connection into a DataFrame.

    Uses a raw cursor rather than ``pd.read_sql`` so that no SQLAlchemy
    engine is required (modern pandas dropped support for bare DBAPI2
    connections in ``pd.read_sql``).

    Parameters
    ----------
    conn:
        An open ``pyodbc.Connection`` (e.g. obtained via :func:`MDBConnection`).
    table_name:
        Name of the table to query.

    Returns
    -------
    pd.DataFrame
        All rows and columns from the specified table.
    """
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)
