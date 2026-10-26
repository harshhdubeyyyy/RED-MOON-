#!/usr/bin/env python3
"""Regenerate the README figures for Forge v2.

Data provenance (read before reusing these numbers anywhere else):
- benchmark_scaling: real output of
    python3 forge.py run examples/benchmark_scaling.fg
  on 26 Oct 2026 (this VM). Times are average microseconds per dot,
  100 repetitions each. Your machine will differ.
- regression_trace: real output of
    python3 forge.py run examples/ml_regression_trace.fg
  on 26 Oct 2026. Targets are the true line y = 2x + 1.
- xor_heatmap: real outputs of examples/ml_mlp_xor.fg
  (sigmoid values, rounded in the plot annotation to 4 decimals).
- loss_3d: computed directly from the regression data points
  xs = [1,2,3,4,5], ys = [3,5,7,9,11] with loss = mean squared
  error over w in [0,3] and b in [-1,2]. It is the mathematical
  loss surface for that example, not a Forge runtime trace.
  The optimum (w=2, b=1, loss=0) is marked.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (needed for 3D)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

RED = "#c1121f"
DARK = "#7f0d17"
GREY = "#555555"
plt.rcParams.update({"font.size": 11, "axes.edgecolor": "#cccccc",
                     "axes.labelcolor": "#222222"})

# 1. Dot-product scaling (real Forge timing) -------------------------------
sizes = np.array([1000, 5000, 10000, 20000])
micros = np.array([1.03, 5.98, 10.67, 21.59])
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(sizes, micros, color=RED, marker="o", markersize=8, linewidth=2.5)
for x, y in zip(sizes, micros):
    ax.annotate(f"{y:.2f} us", (x, y), textcoords="offset points",
                xytext=(0, 10), ha="center", fontsize=10)
ax.set_xlabel("Vector size")
ax.set_ylabel("Average microseconds per dot")
ax.set_title("Forge v2: dot-product latency vs size (safe mode, 100 reps)")
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "benchmark_scaling.png"), dpi=160)
plt.close(fig)

# 2. Regression convergence (real Forge trace) ----------------------------
iters = np.array([0, 100, 200, 300, 400, 500])
w = np.array([0.0, 2.08178, 2.05828, 2.04154, 2.02961, 2.0211])
b = np.array([0.0, 0.704756, 0.789574, 0.850026, 0.893111, 0.923818])
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(iters, w, color=RED, marker="o", label="w (target 2)")
ax.plot(iters, b, color=DARK, marker="s", label="b (target 1)")
ax.axhline(2.0, color=RED, linestyle="--", alpha=0.4)
ax.axhline(1.0, color=DARK, linestyle="--", alpha=0.4)
ax.set_xlabel("Gradient-descent iterations")
ax.set_ylabel("Parameter value")
ax.set_title("Forge v2: linear regression converging to y = 2x + 1")
ax.legend()
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "regression_convergence.png"), dpi=160)
plt.close(fig)

# 3. XOR heatmap (real Forge MLP outputs) ---------------------------------
xor = np.array([[0.000045, 0.999955],
                [0.999955, 0.000045]])
fig, ax = plt.subplots(figsize=(5, 4.5))
im = ax.imshow(xor, cmap="Reds", vmin=0, vmax=1)
ax.set_xticks([0, 1], ["x2 = 0", "x2 = 1"])
ax.set_yticks([0, 1], ["x1 = 0", "x1 = 1"])
ax.set_title("Forge v2 MLP: XOR output (sigmoid)")
for i in range(2):
    for j in range(2):
        ax.text(j, i, f"{xor[i, j]:.4f}", ha="center", va="center",
                fontsize=13, color="white" if xor[i, j] > 0.5 else "#222222")
fig.colorbar(im, ax=ax, label="MLP output")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "xor_heatmap.png"), dpi=160)
plt.close(fig)

# 4. 3D loss surface (computed from the regression data) -----------------
xs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
ys = np.array([3.0, 5.0, 7.0, 9.0, 11.0])
W, B = np.meshgrid(np.linspace(0, 3, 60), np.linspace(-1, 2, 60))
# MSE(w, b) = mean((w*x + b - y)^2), vectorised over the grid.
loss = np.mean((W[..., None] * xs + B[..., None] - ys) ** 2, axis=-1)
fig = plt.figure(figsize=(9, 6))
ax = fig.add_subplot(111, projection="3d")
surf = ax.plot_surface(W, B, loss, cmap="Reds", edgecolor="none", alpha=0.9)
ax.scatter([2.0], [1.0], [0.0], color="black", s=80, marker="*",
           label="Optimum (w=2, b=1, loss=0)")
ax.set_xlabel("w")
ax.set_ylabel("b")
ax.set_zlabel("Mean squared error")
ax.set_title("Forge v2 regression: 3D loss surface over (w, b)")
ax.legend()
fig.colorbar(surf, ax=ax, shrink=0.6, label="MSE")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "loss_3d.png"), dpi=160)
plt.close(fig)

print("Wrote figures to", FIG)
