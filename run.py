import yfinance as yf
import pandas as pd

symbol = "MNQH26.CME"  # later replace with your MNQ data source
data = yf.download(symbol, start="2025-01-01", end="2025-02-12", interval="1h")

# Basic cleaning
data = data.dropna()
print(data.head())
