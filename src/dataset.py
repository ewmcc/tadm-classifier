"""
dataset.py - Discover paired MDB / TXT files in a data directory and assemble
the full TADM dataset by merging pressure curves with gravimetric weights.

File discovery rules:
    - TXT files: ``{RunID}.txt``  (filename stem == RunID)
    - MDB files: ``{prefix}_{RunID}_ML_STAR_tadm.mdb``

Alignment assumption:
    Within a run, CheckSums are sorted lexicographically and aligned
    positionally to the weight rows (first CheckSum → SampleIndex 0, etc.).
    This matches the implicit row-order assumption in the original
    TADM_HamiltonTest.py script.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pandas as pd

from src.curves import STEP_TYPE_ASPIRATE, STEP_TYPE_DISPENSE, extract_curves, parse_runid_from_path
from src.weights import read_weights

_logger = logging.getLogger(__name__)

_STEP_LABELS: dict[int, str] = {
    STEP_TYPE_ASPIRATE: "Aspirate",
    STEP_TYPE_DISPENSE: "Dispense",
}


def find_run_files(data_dir: str | Path) -> list[dict]:
    """Scan *data_dir* and return a list of matched run file pairs.

    Each entry is a dict with keys ``run_id``, ``mdb_path``, ``txt_path``.
    A warning is emitted for any TXT file that has no paired MDB, and vice versa.

    Parameters
    ----------
    data_dir:
        Directory containing ``.txt`` and ``.mdb`` files.

    Returns
    -------
    list[dict]
        One dict per matched run, sorted by ``run_id``.
    """
    data_dir = Path(data_dir).resolve()

    # Index MDB files by their embedded RunID
    mdb_by_runid: dict[str, Path] = {}
    for mdb in data_dir.glob("*.mdb"):
        try:
            run_id = parse_runid_from_path(mdb)
            mdb_by_runid[run_id.lower()] = mdb
        except ValueError:
            warnings.warn(
                f"MDB file does not match expected naming convention and will be "
                f"skipped: {mdb.name}",
                stacklevel=2,
            )

    # Match each TXT file (stem == RunID) to its MDB
    runs: list[dict] = []
    txt_runids: set[str] = set()

    for txt in sorted(data_dir.glob("*.txt")):
        run_id = txt.stem.lower()
        txt_runids.add(run_id)

        if run_id not in mdb_by_runid:
            warnings.warn(
                f"No matching MDB found for TXT file: {txt.name} (RunID={run_id})",
                stacklevel=2,
            )
            continue

        runs.append(
            {
                "run_id": run_id,
                "mdb_path": mdb_by_runid[run_id],
                "txt_path": txt,
            }
        )

    # Warn about MDB files that have no paired TXT
    for run_id, mdb in mdb_by_runid.items():
        if run_id not in txt_runids:
            warnings.warn(
                f"No matching TXT found for MDB file: {mdb.name} (RunID={run_id})",
                stacklevel=2,
            )

    return sorted(runs, key=lambda r: r["run_id"])


def build_dataset(data_dir: str | Path) -> pd.DataFrame:
    """Assemble the full TADM dataset from all matched run file pairs.

    For each run, both aspirate and dispense curves are included. Each step
    type is aligned positionally with the gravimetric weight rows: the nth
    curve of a given step type (sorted by ``CurveId``) is assigned
    ``SampleIndex`` *n*, which maps to the nth row of the weight TXT file.

    Parameters
    ----------
    data_dir:
        Directory containing ``.txt`` and ``.mdb`` files.

    Returns
    -------
    pd.DataFrame
        Columns: ``RunID``, ``CheckSum``, ``StepType``, ``StepLabel``,
        ``ChannelNumber``, ``SampleIndex``, ``CurveTime`` (ms),
        ``CurvePressure``, ``Weight`` (g).
    """
    runs = find_run_files(data_dir)
    if not runs:
        warnings.warn(f"No matched run file pairs found in: {data_dir}", stacklevel=2)
        return pd.DataFrame(
            columns=["RunID", "CheckSum", "StepType", "StepLabel", "ChannelNumber",
                     "SampleIndex", "CurveTime", "CurvePressure", "Weight"]
        )

    all_frames: list[pd.DataFrame] = []

    for run in runs:
        run_id = run["run_id"]
        _logger.info("Loading run: %s", run_id)

        curves = extract_curves(run["mdb_path"])
        weights = read_weights(run["txt_path"])

        step_frames: list[pd.DataFrame] = []

        for step_type, step_label in _STEP_LABELS.items():
            # Unique CheckSums for this step type, in chronological order
            step_unique = (
                curves[curves["StepType"] == step_type]
                .drop_duplicates("CheckSum")
                .sort_values("CurveId")
                .reset_index(drop=True)
            )

            n_step = len(step_unique)
            n_weights = len(weights)

            if n_step != n_weights:
                warnings.warn(
                    f"Run {run_id} [{step_label}]: {n_step} curves vs {n_weights} "
                    "weight rows - counts do not match. The inner merge will keep "
                    "only rows where SampleIndex exists in both tables, so the "
                    "smaller count determines how many samples are included. "
                    "Check that the MDB and TXT files are from the same instrument run.",
                    stacklevel=2,
                )

            # Positional SampleIndex: the nth CheckSum (sorted by CurveId) is mapped
            # to SampleIndex n, which in turn aligns to the nth row of the weight file.
            # This assumes the instrument writes weights in the same order it records
            # curves. If events are missing or reordered in either file, weights will
            # be misassigned.
            step_index = step_unique[["CheckSum"]].copy()
            step_index["SampleIndex"] = range(n_step)

            # Expand back to all time-point rows for this step type
            step_all = (
                curves[curves["StepType"] == step_type]
                .merge(step_index, on="CheckSum", how="left")
                .dropna(subset=["SampleIndex"])
            )
            step_all["SampleIndex"] = step_all["SampleIndex"].astype(int)

            merged = pd.merge(step_all, weights, on=["RunID", "SampleIndex"], how="inner")
            merged["StepLabel"] = step_label
            step_frames.append(merged)

        if step_frames:
            run_df = pd.concat(step_frames, ignore_index=True)
            all_frames.append(
                run_df[["RunID", "CheckSum", "StepType", "StepLabel", "ChannelNumber",
                         "SampleIndex", "CurveTime", "CurvePressure", "Weight"]]
            )

    return pd.concat(all_frames, ignore_index=True)
