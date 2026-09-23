# StockPilot — Feature-Rich Stock Market Prediction Web App

A Flask-based educational stock analytics dashboard with:
- User registration/login/logout
- Password hashing
- SQLite persistence
- NSE/BSE/US ticker support through yfinance
- Random Forest next-session UP/DOWN classification
- Time-based 80/20 train/test split (no random shuffle)
- Cached models per ticker
- SMA, EMA, RSI, MACD, volatility, lag and volume features
- 60-session Chart.js price chart
- Personal watchlist
- Portfolio/holdings tracker with P/L
- Price alerts checked on dashboard refresh
- Indian-market quick buttons (NIFTY 50, SENSEX, BANK NIFTY and popular NSE stocks)
- Responsive dark dashboard
- JSON APIs for predictions, quotes, watchlist, portfolio and alerts

## 1. Open in VS Code

Extract the ZIP, then:
File → Open Folder → `stock_market_prediction_app_pro`

Open Terminal → New Terminal.

## 2. Create virtual environment

Windows PowerShell:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can run:
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

## 3. Install packages

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Run

```powershell
python app.py
```

Open:
http://127.0.0.1:5000

## 5. Indian symbols

Examples:
- `RELIANCE.NS`
- `TCS.NS`
- `INFY.NS`
- `HDFCBANK.NS`
- `ICICIBANK.NS`
- `SBIN.NS`
- `ITC.NS`
- `BHARTIARTL.NS`
- `TATAMOTORS.NS`
- `^NSEI` (NIFTY 50)
- `^BSESN` (SENSEX)
- `^NSEBANK` (BANK NIFTY)

## Important notes

1. Yahoo Finance availability and data can change. A ticker may fail if Yahoo does not provide data for it.
2. The first analysis for a ticker downloads about five years of data and trains a model; a model is saved under `models/`.
3. The model is an educational experiment. It does not know future news, order flow, corporate actions or market shocks.
4. The price-alert feature checks current data when the dashboard loads/refreshes. It does not send background push/email notifications by itself.
5. For production deployment, change `app.secret_key`, use HTTPS, add CSRF protection, secure cookies, a production WSGI server, stronger validation/rate limits and a managed database.
6. Never store real production secrets in source code.

## Optional manual model training

```powershell
python train_model.py RELIANCE.NS
```

## Main files

- `app.py` — Flask routes, authentication, SQLite, APIs
- `features.py` — indicators and ML features
- `train_model.py` — model training/caching
- `templates/` — dashboard and authentication pages
- `static/` — CSS and browser JavaScript
- `models/` — cached model artifacts
- `stockapp.db` — created automatically on first run

## Educational disclaimer

This application is for education and software demonstration only. Predictions and indicators are not financial advice and are not guarantees of future returns.
