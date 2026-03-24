import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

base_dir = Path("/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1")

seen = set()
for cut_file in base_dir.rglob("*.17merFreq.*.cut"):
    data_dir = cut_file.parent
    file_stem = cut_file.stem.replace(".17merFreq.NumFreq", "").replace(".17merFreq.SpeFreq", "")

    # skip stems we've already processed (rglob returns both NumFreq and SpeFreq files)
    if file_stem in seen:
        continue
    seen.add(file_stem)

    # read both numeric and species frequency files and plot together
    curves = {}
    for name, color in [("NumFreq", "blue"), ("SpeFreq", "red")]:
        file_path = data_dir / f"{file_stem}.17merFreq.{name}.cut"
        if not file_path.exists():
            continue

        df = pd.read_csv(file_path, sep=r"\s+", header=None, names=["Depth", "Frequency"])
        df["Depth"] = pd.to_numeric(df["Depth"], errors="coerce")
        df = df[df["Depth"] <= 300]
        curves[name] = (df, color)

    if not curves:
        continue

    plt.figure(figsize=(8, 5))
    for name, (df, color) in curves.items():
        plt.plot(df["Depth"], df["Frequency"], color=color, label=name)
    plt.title(f"17-mer frequencies ({file_stem})")
    plt.xlabel("Depth")
    plt.ylabel("Frequency")
    plt.yscale("log")   # log scale helps see both curves when values differ greatly
    plt.legend()
    plt.tight_layout()

    output_path = data_dir / f"Sdis.17mer.combined.pdf"
    plt.savefig(output_path)
    plt.close()
    print(f"Saved: {output_path}")
