import pandas as pd
import numpy as np
from scipy.signal import savgol_filter

filepath = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2501/X101SC25015691-Z01-J020/FDES250046014-1r_CNS02440-1/CNS02440-1.17merFreq.SpeFreq.cut'

df = pd.read_csv(filepath, sep=r'\s+', header=None, names=['Depth', 'Frequency'])
df = df[(df['Depth'] >= 3) & (df['Depth'] <= 300)]
df = df.sort_values('Depth').reset_index(drop=True)

freq = df['Frequency'].values.astype(float)
depth = df['Depth'].values
freq_smooth = savgol_filter(freq, window_length=11, polyorder=3)

# 找深度9附近的峰
peak_idx = np.where(depth == 9)[0][0]
peak_freq = freq_smooth[peak_idx]
half_height = peak_freq / 2

print(f"深度9的峰:")
print(f"  峰高度: {peak_freq:.0f}")
print(f"  半高: {half_height:.0f}")

# 找左边界
left = peak_idx
while left > 0 and freq_smooth[left] > half_height:
    left -= 1

# 找右边界
right = peak_idx
while right < len(freq_smooth) - 1 and freq_smooth[right] > half_height:
    right += 1

width = right - left
print(f"  半高宽: {width}")
print(f"\n深度范围: {depth[left]} 到 {depth[right]}")
print(f"频率值:")
for i in range(max(0, left-2), min(len(depth), right+3)):
    marker = " <-- 峰" if i == peak_idx else ""
    print(f"  depth={depth[i]}, freq={freq_smooth[i]:.0f}{marker}")
