from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
THRESHOLD = 0.85
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2dd"
TRUSTED, SUSPECT = "#2a78d6", "#eb6834"

df = pd.read_csv(ROOT / "data" / "epl_matches_2000_2026.csv", dtype={"Season": str})
df["season"] = 2000 + df["Season"].str[:2].astype(int)
played = df[(df["Attendance"] > 0) & df["HomeStadium"].notna()][["season", "HomeStadium", "Attendance"]]

stats, frames = {}, {}
for season, group in played.groupby("season"):
    baseline = played[played["season"] != season].groupby("HomeStadium")["Attendance"].median()
    cmp = group.assign(typical=group["HomeStadium"].map(baseline)).dropna(subset=["typical"])
    stats[season] = cmp["Attendance"].corr(cmp["typical"]) if len(cmp) > 2 else 0.0
    frames[season] = cmp

plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
                     "xtick.color": INK_2, "ytick.color": INK_2, "text.color": INK})
fig = plt.figure(figsize=(11, 7.6), facecolor=SURFACE)
grid = fig.add_gridspec(2, 2, height_ratios=[1.05, 1], hspace=0.5, wspace=0.18)

ax = fig.add_subplot(grid[0, :], facecolor=SURFACE)
seasons = list(stats)
colors = [TRUSTED if stats[s] >= THRESHOLD else SUSPECT for s in seasons]
ax.bar([str(s) for s in seasons], [stats[s] for s in seasons], color=colors, edgecolor=SURFACE, linewidth=2)
ax.axhline(THRESHOLD, color=INK_2, linewidth=1, linestyle="--")
ax.text(len(seasons) - 0.4, THRESHOLD + 0.03, "порог 0,85", ha="right", color=INK_2, fontsize=10)
ax.text(seasons.index(2019), 0.04, "≈ 0", ha="center", color=INK_2, fontsize=10)
ax.set_ylim(0, 1.08)
ax.set_ylabel("корреляция с типичной\nпосещаемостью стадиона")
ax.set_xlabel("год начала сезона")
ax.tick_params(axis="x", labelrotation=90, length=0)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.set_title("Посещаемость в CSV по сезонам", loc="left", color=INK, fontsize=12)
ax.legend(handles=[Patch(color=TRUSTED, label="достоверно"), Patch(color=SUSPECT, label="недостоверно")],
          loc="lower right", bbox_to_anchor=(1.0, 1.0), frameon=False, ncol=2, fontsize=10, labelcolor=INK_2)

for slot, (season, title) in enumerate(((2022, "2022/23: данные согласованы"),
                                        (2024, "2024/25: не связаны со стадионом"))):
    sub = fig.add_subplot(grid[1, slot], facecolor=SURFACE)
    cmp = frames[season]
    color = TRUSTED if stats[season] >= THRESHOLD else SUSPECT
    sub.scatter(cmp["typical"] / 1000, cmp["Attendance"] / 1000, s=14, color=color, alpha=0.7,
                edgecolors=SURFACE, linewidths=0.6)
    sub.plot([5, 85], [5, 85], color=INK_2, linewidth=1, linestyle="--")
    sub.set_xlim(5, 85)
    sub.set_ylim(0, 85)
    sub.set_xlabel("типичная посещаемость стадиона, тыс.")
    if slot == 0:
        sub.set_ylabel("посещаемость в CSV, тыс.")
    sub.set_title(f"{title} (r = {stats[season]:.2f})".replace(".", ","), loc="left", color=INK, fontsize=11)
    sub.grid(True, color=GRID, linewidth=0.8)
    sub.set_axisbelow(True)
    for side in ("top", "right"):
        sub.spines[side].set_visible(False)

out = ROOT / "docs" / "attendance_quality.png"
out.parent.mkdir(exist_ok=True)
fig.savefig(out, dpi=160, facecolor=SURFACE, bbox_inches="tight")
print(out)
