"""
curves.py - Extract TADM pressure curves from an MDB file.

The TadmCurve table has one row per pipetting event. The ``CurvePoints``
column is a binary blob encoding a pressure waveform sampled every 10 ms
as a sequence of little-endian signed 16-bit integers (``int16``).

Two step types are present in each run:
    - ``STEP_TYPE_ASPIRATE`` (-533331728) - pressure during liquid uptake
    - ``STEP_TYPE_DISPENSE`` (-533331727) - pressure during liquid delivery

Each event is identified by a unique ``CheckSum`` and ordered
chronologically by ``CurveId``.

The RunID is extracted from the MDB filename, which follows the convention:
    {prefix}_{RunID}_ML_STAR_tadm.mdb
"""

from __future__ import annotations

import re
import struct
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src.db import mdb_connection, read_table

# Regex to pull the RunID out of the MDB filename
_RUNID_PATTERN = re.compile(r"_([a-f0-9]{32})_ML_STAR_tadm\.mdb$", re.IGNORECASE)

# Hamilton VENUS step type identifiers stored in TadmCurve.StepType
STEP_TYPE_ASPIRATE: int = -533331728
STEP_TYPE_DISPENSE: int = -533331727


def parse_runid_from_path(mdb_path: Path) -> str:
    """Extract the 32-character hex RunID from an MDB filename."""
    match = _RUNID_PATTERN.search(mdb_path.name)
    if not match:
        raise ValueError(
            f"Could not extract RunID from MDB filename: {mdb_path.name}\n"
            "Expected pattern: {prefix}_{RunID}_ML_STAR_tadm.mdb"
        )
    return match.group(1)


def parse_curve_points(blob: bytes) -> list[int]:
    """Decode a CurvePoints binary blob into a list of pressure values.

    Each waveform is stored as a sequence of little-endian signed 16-bit
    integers (``int16``), one per 10 ms time step.

    Parameters
    ----------
    blob:
        Raw bytes from the ``CurvePoints`` column of a single TadmCurve row.

    Returns
    -------
    list[int]
        Pressure values in chronological order (10 ms resolution).
    """
    # Each pressure sample is stored as a little-endian signed 16-bit integer.
    # Two bytes per sample, so the number of samples is the byte length divided by 2.
    n_samples = len(blob) // 2

    # Format string for struct.unpack: '<' = little-endian, 'h' = signed 16-bit int.
    # The slice ensures we only read complete 2-byte pairs and discard any trailing byte.
    fmt = f"<{n_samples}h"
    return list(struct.unpack(fmt, blob[: n_samples * 2]))


def extract_curves(mdb_path: str | Path) -> pd.DataFrame:
    """Read an MDB file and return all TADM curves as a long-format DataFrame.

    Each row in the TadmCurve table represents one pipetting event (aspirate
    or dispense). The binary CurvePoints blob is decoded into individual
    pressure values and a CurveTime column is added (milliseconds, 10 ms
    resolution). Rows are ordered by CurveId (chronological instrument order).

    Parameters
    ----------
    mdb_path:
        Path to the ``.mdb`` file.

    Returns
    -------
    pd.DataFrame
        Columns: ``RunID``, ``CurveId``, ``CheckSum``, ``StepType``,
        ``ChannelNumber``, ``CurveTime`` (ms), ``CurvePressure``.
    """
    mdb_path = Path(mdb_path).resolve()
    run_id = parse_runid_from_path(mdb_path)

    with mdb_connection(mdb_path) as conn:
        raw = read_table(conn, "TadmCurve")

    raw = raw.sort_values("CurveId").reset_index(drop=True)

    frames: list[pd.DataFrame] = []

    for _, row in raw.iterrows():
        pressure = parse_curve_points(row["CurvePoints"])
        frames.append(
            pd.DataFrame(
                {
                    "RunID": run_id,
                    "CurveId": row["CurveId"],
                    "CheckSum": row["CheckSum"],
                    "StepType": row["StepType"],
                    "ChannelNumber": row["ChannelNumber"],
                    "CurveTime": np.arange(len(pressure)) * 10,
                    "CurvePressure": pressure,
                }
            )
        )

    if not frames:
        warnings.warn(f"No curves found in {mdb_path.name}", stacklevel=2)
        return pd.DataFrame(
            columns=["RunID", "CurveId", "CheckSum", "StepType", "ChannelNumber", "CurveTime", "CurvePressure"]
        )

    return pd.concat(frames, ignore_index=True)
