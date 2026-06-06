"""
weights.py - Read gravimetric weight files produced by the liquid handler balance.

Each TXT file corresponds to one instrument run and contains a single column of
quoted float values (one weight per pipetting event) with the header ``"Weight"``.
The filename stem is the RunID, matching the RunID encoded in the paired MDB filename.

Example file layout::

    "Weight"
    "0.04013"
    "0.04521"
    ...
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_weights(txt_path: str | Path) -> pd.DataFrame:
    """Parse a gravimetric weight TXT file into a DataFrame.

    Parameters
    ----------
    txt_path:
        Path to the ``.txt`` file whose stem is the RunID.

    Returns
    -------
    pd.DataFrame
        Columns: ``RunID``, ``SampleIndex`` (0-based), ``Weight`` (float, grams).
    """
    txt_path = Path(txt_path).resolve()
    run_id = txt_path.stem

    df = pd.read_csv(txt_path, header=0)
    # The instrument writes each value as a quoted string, e.g. "0.04013".
    # Strip the surrounding double-quote characters before converting to float.
    col = df.columns[0]
    df[col] = df[col].astype(str).str.strip('"').astype(float)
    df = df.rename(columns={col: "Weight"})

    df.insert(0, "RunID", run_id)
    df.insert(1, "SampleIndex", range(len(df)))

    return df[["RunID", "SampleIndex", "Weight"]]
