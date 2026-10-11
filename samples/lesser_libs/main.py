import json
import math
import numpy as np
import pandas as pd

print("--> [Python] Running computation using pre-installed numpy and pandas...")

data = {
    "iteration": list(range(1, 11)),
    "sine_val": [round(math.sin(i), 4) for i in range(1, 11)],
    "np_square": np.square(np.arange(1, 11)).tolist()
}
df = pd.DataFrame(data)
df["cumsum_square"] = df["np_square"].cumsum()

print("--> [Python] DataFrame preview:")
print(df.to_string(index=False))

# Save output files
df.to_csv("processed_data.csv", index=False)

summary = {
    "status": "success",
    "total_rows": len(df),
    "mean_square": float(df["np_square"].mean()),
    "description": "Executed successfully with pre-installed base libraries."
}

with open("summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print("--> [Python] Generated artifacts: processed_data.csv and summary.json")
