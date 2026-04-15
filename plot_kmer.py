import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

base_dir = Path("data/FDES250026022-1a_Sdis/01Survey")

seen = set()
for cut_file in base_dir.rglob("*.17merFreq.*.cut"):
    data_dir = cut_file.parent
    file_stem = cut_file.stem.replace(".17merFreq.NumFreq", "").replace(".17merFreq.SpeFreq", "")

    # skip stems we've already processed (rglob returns both NumFreq and SpeFreq files)
    if file_stem in seen:
        continue
    seen.add(file_stem)

    # read numeric/species frequency files and plot separately
    for name, color in [("NumFreq", "blue"), ("SpeFreq", "red")]:
        file_path = data_dir / f"{file_stem}.17merFreq.{name}.cut"
        if not file_path.exists():
            continue

        df = pd.read_csv(file_path, sep=r"\s+", header=None, names=["Depth", "Frequency"])
        df["Depth"] = pd.to_numeric(df["Depth"], errors="coerce")
        df = df[df["Depth"] <= 300]

        if df.empty:
            continue

        plt.figure(figsize=(8, 5))
        plt.plot(df["Depth"], df["Frequency"], color=color, label=name)
        plt.title(f"17-mer {name} ({file_stem})")
        plt.xlabel("Depth")
        plt.ylabel("Frequency")
        if name == "SpeFreq":
            # SpeFreq often has an extreme spike at very low depth (e.g. depth 1-5),
            # which can hide the biologically meaningful main peak.
            # Use depth>=10 to estimate a robust y-axis upper bound for visibility.
            main_region = df[df["Depth"] >= 10]["Frequency"]
            if not main_region.empty:
                y_top = main_region.max() * 1.15
                if y_top > 0:
                    plt.ylim(0, y_top)
                if df["Frequency"].max() > y_top:
                    plt.text(
                        0.02,
                        0.96,
                        "Low-depth spike truncated",
                        transform=plt.gca().transAxes,
                        va="top",
                        ha="left",
                        fontsize=9,
                        color="gray",
                    )
        # Keep independent y-axis autoscaling for each figure.
        plt.legend()
        plt.tight_layout()

        output_path = data_dir / f"Sdis.17mer.{name}.pdf"
        plt.savefig(output_path)
        plt.close()
        print(f"Saved: {output_path}")
