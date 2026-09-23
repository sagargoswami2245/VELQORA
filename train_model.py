from pathlib import Path
from datetime import datetime, timezone
import joblib
import yfinance as yf

from features import train_classifier, feature_columns_expected

def download_history(ticker):
    data = yf.download(ticker, period="5y", interval="1d", auto_adjust=False, progress=False, threads=False)
    if data is None or data.empty:
        raise ValueError(f"No market data found for {ticker}.")
    if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
        if ticker in data.columns.get_level_values(-1):
            data = data.xs(ticker, axis=1, level=-1, drop_level=True)
        elif ticker in data.columns.get_level_values(0):
            data = data.xs(ticker, axis=1, level=0, drop_level=True)
        else:
            data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
    return data

def train_and_save(ticker, model_path, downloader=download_history):
    data = downloader(ticker)
    model, metrics = train_classifier(data)
    artifact = {
        "model": model,
        "feature_columns": feature_columns_expected(),
        "metrics": metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    return artifact

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python train_model.py AAPL")
    ticker = sys.argv[1].upper()
    artifact = train_and_save(ticker, Path("models") / f"{ticker}.pkl")
    print(f"Saved {ticker} model. Test accuracy: {artifact['metrics']['test_accuracy']:.2%}")
