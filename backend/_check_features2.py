import sys

sys.path.insert(0, 'backend')

import warnings

from scripts.train_real_ml import FEATURE_NAMES
from services.ml.inference import compute_live_features

warnings.filterwarnings('ignore')

# Actually compute features on real SPY data
print("Computing live features on SPY...")
df = compute_live_features("SPY", period="3mo")
computed_cols = set(df.columns)
train_cols = set(FEATURE_NAMES)

print(f"\nTraining FEATURE_NAMES ({len(train_cols)}): {sorted(train_cols)}")
print(f"\ncompute_live_features columns ({len(computed_cols)}): {sorted(computed_cols)}")
print(f"\nIn training but NOT in computed ({len(train_cols - computed_cols)}):")
for f in sorted(train_cols - computed_cols):
    print(f"  - {f}")
print(f"\nIn computed but NOT in training ({len(computed_cols - train_cols)}):")
for f in sorted(computed_cols - train_cols):
    print(f"  + {f}")
print(f"\nIntersection: {len(train_cols & computed_cols)} features match")
