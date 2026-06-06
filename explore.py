"""
explore.py - Data exploration entrypoint for the tadm-classifier repository.

Loads all matched run files from data/, prints a dataset summary, and
produces two plots:

  1. TADM curves - all pressure waveforms faceted by step type (Aspirate /
     Dispense), giving an immediate visual sense of the waveform variation.

  2. Weight distribution - a histogram of all gravimetric weights across every
     run in the dataset, useful for choosing classification thresholds later.

Run from the repo root::

    python explore.py
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt

from src.dataset import build_dataset

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

DATA_DIR = "data"
OUTPUT_DIR = Path("output")


def main() -> None:
    # -- Load ------------------------------------------------------------------
    print("Loading dataset …")
    df = build_dataset(DATA_DIR)

    if df.empty:
        print("No data loaded - check that data/ contains matched MDB and TXT files.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # -- Summary ---------------------------------------------------------------
    n_runs = df["RunID"].nunique()
    n_timepoints = len(df)
    curves_per_step = (
        df.drop_duplicates(["RunID", "CheckSum"])
        .groupby("StepLabel")["CheckSum"]
        .count()
    )

    print(f"\nRuns: {n_runs}")
    print(f"Time points: {n_timepoints:,}")
    print(f"\nCurves by step type:\n{curves_per_step.to_string()}")
    print(f"\nDataFrame shape: {df.shape}")
    print(f"\nDtypes:\n{df.dtypes}")
    print(f"\nWeight stats (g):\n{df.drop_duplicates(['RunID', 'SampleIndex'])['Weight'].describe()}")

    # -- Export dataset --------------------------------------------------------
    csv_path = OUTPUT_DIR / "dataset.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nDataset saved → {csv_path}")

    # -- Plot 1 - TADM pressure waveforms (all curves, faceted by step type) --
    step_labels = sorted(df["StepLabel"].unique())
    fig, axes = plt.subplots(1, len(step_labels), figsize=(14, 7), sharey=True)
    if len(step_labels) == 1:
        axes = [axes]
    for ax, label in zip(axes, step_labels):
        subset = df[df["StepLabel"] == label].sort_values("CurveTime")
        for _, group in subset.groupby("CheckSum"):
            ax.plot(group["CurveTime"], group["CurvePressure"],
                    linewidth=0.8, alpha=0.5, color="steelblue")
        ax.set_title(label)
        ax.set_xlabel("Time (ms)")
    axes[0].set_ylabel("Pressure (Pa)")
    plt.tight_layout()
    fig_path = OUTPUT_DIR / "tadm_pressure_curves.png"
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    print(f"Plot saved → {fig_path}")

    # -- Plot 2 - Weight distribution -----------------------------------------
    weights = df.drop_duplicates(["RunID", "SampleIndex"])["Weight"]

    fig2, ax2 = plt.subplots(figsize=(8, 4))
    ax2.hist(weights, bins=30, color="steelblue", edgecolor="white")
    ax2.set_xlabel("Weight (g)")
    ax2.set_ylabel("Count")
    plt.tight_layout()
    fig2_path = OUTPUT_DIR / "weight_distribution.png"
    fig2.savefig(fig2_path, dpi=150)
    plt.close(fig2)
    print(f"Plot saved → {fig2_path}")


if __name__ == "__main__":
    main()
