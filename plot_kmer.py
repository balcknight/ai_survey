import pandas as pd
import matplotlib.pyplot as plt

data_dir = "FDES250026022-1a_Sdis/01Survey"
output_dir = "./"
for name, color in [("NumFreq", "blue"), ("SpeFreq", "red")]:
    df = pd.read_csv(f"{data_dir}/Sdis.17merFreq.{name}.cut", sep=r"\s+", header=None, names=["Depth", "Frequency"])
    # 确保 Depth 是数值型
    df["Depth"] = pd.to_numeric(df["Depth"], errors="coerce")
    # 过滤掉 Depth 大于 300 的数据点
    df = df[df["Depth"] <= 300]
    print(f"Plotting {name} with {len(df)} data points...")
    plt.figure(figsize=(8, 5))
    plt.plot(df["Depth"], df["Frequency"], color=color)
    plt.title(f"17-mer {name}")
    plt.xlabel("Depth")
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(f"{output_dir}/Sdis.17mer.{name}.pdf")
    plt.close()
    print(f"Saved: {output_dir}/Sdis.17mer.{name}.pdf")
