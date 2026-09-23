import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

FEATURE_COLUMNS = [
    "sma_5", "sma_10", "sma_20", "ema_10", "rsi_14",
    "macd", "macd_signal", "rolling_volatility",
    "close_lag_1", "close_lag_2", "close_lag_3", "volume_change",
]

def feature_columns_expected():
    return FEATURE_COLUMNS.copy()

def compute_indicators(data):
    df = data.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Volume"] = pd.to_numeric(df.get("Volume", 0), errors="coerce").fillna(0)

    df["sma_5"] = df["Close"].rolling(5).mean()
    df["sma_10"] = df["Close"].rolling(10).mean()
    df["sma_20"] = df["Close"].rolling(20).mean()
    df["ema_10"] = df["Close"].ewm(span=10, adjust=False).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = (100 - (100 / (1 + rs))).fillna(50)

    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    returns = df["Close"].pct_change()
    df["rolling_volatility"] = returns.rolling(20).std()
    df["close_lag_1"] = df["Close"].shift(1)
    df["close_lag_2"] = df["Close"].shift(2)
    df["close_lag_3"] = df["Close"].shift(3)
    df["volume_change"] = df["Volume"].pct_change().replace([np.inf, -np.inf], np.nan)

    return df

def build_feature_dataframe(data):
    df = compute_indicators(data)
    df["target"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
    return df

def prepare_training_data(data):
    df = build_feature_dataframe(data).dropna(subset=FEATURE_COLUMNS + ["target"]).copy()
    if len(df) < 120:
        raise ValueError("Not enough historical data to train this model.")
    split = int(len(df) * 0.8)
    if split <= 0 or split >= len(df):
        raise ValueError("Could not create a time-based train/test split.")
    X_train, X_test = df[FEATURE_COLUMNS].iloc[:split], df[FEATURE_COLUMNS].iloc[split:]
    y_train, y_test = df["target"].astype(int).iloc[:split], df["target"].astype(int).iloc[split:]
    return X_train, X_test, y_train, y_test

def train_classifier(data):
    X_train, X_test, y_train, y_test = prepare_training_data(data)
    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    accuracy = float(model.score(X_test, y_test))
    return model, {
        "test_accuracy": round(accuracy, 4),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
    }

def make_prediction(model, data, feature_columns, metrics=None, trained_at=None):
    df = compute_indicators(data)
    usable = df.dropna(subset=feature_columns).copy()
    if usable.empty:
        raise ValueError("Not enough recent data to calculate indicators.")
    latest = usable.iloc[-1]
    X = usable[feature_columns].iloc[[-1]]
    pred = int(model.predict(X)[0])
    probs = model.predict_proba(X)[0]
    confidence = float(probs[pred] * 100)
    close = float(latest["Close"])
    dates = usable.index
    prices = [{"date": d.strftime("%Y-%m-%d"), "close": round(float(df.loc[d, "Close"]), 2)} for d in dates[-60:]]
    return {
        "ticker": getattr(data, "name", None) or "",
        "predicted_direction": "UP" if pred == 1 else "DOWN",
        "confidence": round(confidence, 2),
        "last_close": round(close, 2),
        "last_date": usable.index[-1].strftime("%Y-%m-%d"),
        "prices": prices,
        "metrics": metrics or {},
        "trained_at": trained_at,
        "indicators": {
            "rsi_14": round(float(latest["rsi_14"]), 2),
            "macd": round(float(latest["macd"]), 4),
            "macd_signal": round(float(latest["macd_signal"]), 4),
            "sma_20": round(float(latest["sma_20"]), 2),
            "ema_10": round(float(latest["ema_10"]), 2),
            "volatility": round(float(latest["rolling_volatility"]) * 100, 2),
        },
    }
