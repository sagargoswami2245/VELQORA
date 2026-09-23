from pathlib import Path
import json
import sqlite3
from datetime import datetime
from functools import wraps
import re

import yfinance as yf
from flask import Flask, jsonify, redirect, render_template, request, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

from features import (
    build_feature_dataframe,
    feature_columns_expected,
    make_prediction,
)
from train_model import train_and_save

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
DB_PATH = BASE_DIR / "stockapp.db"

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION"
app.config["JSON_SORT_KEYS"] = False

TICKER_RE = re.compile(r"^[A-Z0-9.\-^=]{1,25}$")

POPULAR_INDIAN = [
    ("NIFTY 50", "^NSEI"),
    ("SENSEX", "^BSESN"),
    ("BANK NIFTY", "^NSEBANK"),
    ("RELIANCE", "RELIANCE.NS"),
    ("TCS", "TCS.NS"),
    ("INFOSYS", "INFY.NS"),
    ("HDFC BANK", "HDFCBANK.NS"),
    ("ICICI BANK", "ICICIBANK.NS"),
    ("SBI", "SBIN.NS"),
    ("ITC", "ITC.NS"),
    ("BHARTI AIRTEL", "BHARTIARTL.NS"),
    ("TATA MOTORS", "TATAMOTORS.NS"),
    ("LT", "LT.NS"),
    ("ADANI ENTERPRISES", "ADANIENT.NS"),
]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        UNIQUE(user_id, ticker),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        quantity REAL NOT NULL,
        avg_price REAL NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, ticker),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        target_price REAL NOT NULL,
        direction TEXT NOT NULL CHECK(direction IN ('above','below')),
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"success": False, "error": "Please log in first."}), 401
        return fn(*args, **kwargs)
    return wrapper

def page_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def normalize_ticker(raw):
    ticker = (raw or "").strip().upper()
    if not ticker:
        raise ValueError("Enter a ticker symbol.")
    if not TICKER_RE.fullmatch(ticker):
        raise ValueError("Invalid ticker. Example: RELIANCE.NS or AAPL.")
    return ticker

def download_history(ticker):
    data = yf.download(
        ticker,
        period="5y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
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

def current_snapshot(ticker):
    data = download_history(ticker)
    if "Close" not in data.columns:
        raise ValueError("Yahoo Finance did not return a Close column.")
    closes = data["Close"].dropna()
    if closes.empty:
        raise ValueError(f"No closing prices found for {ticker}.")
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) > 1 else last
    change = last - prev
    pct = (change / prev * 100) if prev else 0
    return {
        "ticker": ticker,
        "last_close": round(last, 2),
        "previous_close": round(prev, 2),
        "change": round(change, 2),
        "change_pct": round(pct, 2),
        "last_date": closes.index[-1].strftime("%Y-%m-%d"),
    }

def load_or_train(ticker):
    model_path = MODEL_DIR / f"{ticker.replace('/', '_')}.pkl"
    if model_path.exists():
        import joblib
        artifact = joblib.load(model_path)
        if artifact.get("feature_columns") == feature_columns_expected():
            return artifact
    return train_and_save(ticker, model_path, download_history)

def full_prediction(ticker):
    artifact = load_or_train(ticker)
    data = download_history(ticker)
    return make_prediction(
        artifact["model"],
        data,
        artifact["feature_columns"],
        artifact.get("metrics", {}),
        artifact.get("trained_at"),
    )

@app.context_processor
def inject_globals():
    return {
        "logged_in": "user_id" in session,
        "user_name": session.get("user_name"),
        "popular_indian": POPULAR_INDIAN,
    }

@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("home"))
        flash("Invalid email or password.", "error")
    return render_template("auth.html", mode="login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 2 or "@" not in email or len(password) < 6:
            flash("Use a valid name, email and password of at least 6 characters.", "error")
            return render_template("auth.html", mode="register")
        conn = db()
        try:
            conn.execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                (name, email, generate_password_hash(password), datetime.utcnow().isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash("That email is already registered.", "error")
            return render_template("auth.html", mode="register")
        conn.close()
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("auth.html", mode="register")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/predict")
def api_predict():
    try:
        ticker = normalize_ticker(request.args.get("ticker"))
        result = full_prediction(ticker)
        return jsonify({"success": True, **result})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Prediction error")
        return jsonify({"success": False, "error": f"Could not analyze {request.args.get('ticker','stock')}: {exc}"}), 500

@app.route("/api/quote")
def api_quote():
    try:
        ticker = normalize_ticker(request.args.get("ticker"))
        return jsonify({"success": True, **current_snapshot(ticker)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

@app.route("/api/watchlist")
@login_required
def get_watchlist():
    conn = db()
    rows = conn.execute("SELECT ticker FROM watchlist WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()
    conn.close()
    return jsonify({"success": True, "items": [r["ticker"] for r in rows]})

@app.route("/api/watchlist", methods=["POST"])
@login_required
def add_watchlist():
    try:
        ticker = normalize_ticker(request.json.get("ticker"))
        conn = db()
        conn.execute("INSERT OR IGNORE INTO watchlist(user_id,ticker) VALUES(?,?)", (session["user_id"], ticker))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "ticker": ticker})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

@app.route("/api/watchlist/<path:ticker>", methods=["DELETE"])
@login_required
def delete_watchlist(ticker):
    conn = db()
    conn.execute("DELETE FROM watchlist WHERE user_id=? AND ticker=?", (session["user_id"], normalize_ticker(ticker)))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/portfolio")
@login_required
def portfolio():
    conn = db()
    rows = conn.execute("SELECT id,ticker,quantity,avg_price FROM holdings WHERE user_id=? ORDER BY ticker", (session["user_id"],)).fetchall()
    conn.close()
    items = []
    total_value = 0.0
    total_cost = 0.0
    for row in rows:
        try:
            snap = current_snapshot(row["ticker"])
            value = snap["last_close"] * row["quantity"]
            cost = row["avg_price"] * row["quantity"]
            pnl = value - cost
            items.append({**dict(row), "last_price": snap["last_close"], "value": round(value,2), "pnl": round(pnl,2), "pnl_pct": round((pnl/cost*100) if cost else 0,2)})
            total_value += value
            total_cost += cost
        except Exception:
            items.append({**dict(row), "last_price": None, "value": None, "pnl": None, "pnl_pct": None})
    return jsonify({"success": True, "items": items, "total_value": round(total_value,2), "total_cost": round(total_cost,2), "total_pnl": round(total_value-total_cost,2)})

@app.route("/api/portfolio", methods=["POST"])
@login_required
def add_holding():
    data = request.json or {}
    try:
        ticker = normalize_ticker(data.get("ticker"))
        qty = float(data.get("quantity"))
        price = float(data.get("avg_price"))
        if qty <= 0 or price <= 0:
            raise ValueError("Quantity and average price must be positive.")
        conn = db()
        existing = conn.execute("SELECT * FROM holdings WHERE user_id=? AND ticker=?", (session["user_id"], ticker)).fetchone()
        if existing:
            old_qty = existing["quantity"]
            new_qty = old_qty + qty
            new_avg = ((old_qty * existing["avg_price"]) + (qty * price)) / new_qty
            conn.execute("UPDATE holdings SET quantity=?, avg_price=? WHERE id=?", (new_qty, new_avg, existing["id"]))
        else:
            conn.execute("INSERT INTO holdings(user_id,ticker,quantity,avg_price,created_at) VALUES(?,?,?,?,?)", (session["user_id"],ticker,qty,price,datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

@app.route("/api/portfolio/<int:holding_id>", methods=["DELETE"])
@login_required
def delete_holding(holding_id):
    conn = db()
    conn.execute("DELETE FROM holdings WHERE id=? AND user_id=?", (holding_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/alerts")
@login_required
def get_alerts():
    conn = db()
    rows = conn.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        try:
            price = current_snapshot(row["ticker"])["last_close"]
            item["current_price"] = price
            item["triggered"] = (price >= row["target_price"]) if row["direction"] == "above" else (price <= row["target_price"])
        except Exception:
            item["current_price"] = None
            item["triggered"] = False
        result.append(item)
    return jsonify({"success": True, "items": result})

@app.route("/api/alerts", methods=["POST"])
@login_required
def create_alert():
    data = request.json or {}
    try:
        ticker = normalize_ticker(data.get("ticker"))
        target = float(data.get("target_price"))
        direction = data.get("direction")
        if target <= 0 or direction not in ("above", "below"):
            raise ValueError("Enter a valid target price and direction.")
        conn = db()
        conn.execute("INSERT INTO alerts(user_id,ticker,target_price,direction,created_at) VALUES(?,?,?,?,?)", (session["user_id"],ticker,target,direction,datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

@app.route("/api/alerts/<int:alert_id>", methods=["DELETE"])
@login_required
def delete_alert(alert_id):
    conn = db()
    conn.execute("DELETE FROM alerts WHERE id=? AND user_id=?", (alert_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
