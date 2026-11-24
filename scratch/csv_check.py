from pathlib import Path

import pandas as pd

CSV_PATH = Path(__file__).resolve().parent.parent / 'data' / 'epl_matches_2000_2026.csv'

df = pd.read_csv(CSV_PATH, dtype={'Season': str})
print(df[df['Season'] == '2324'].shape)
print(df.columns.tolist())
print(df.shape)
print(df['Attendance'].isna().sum())
print(df[df['Season'] == '2324'].shape)
