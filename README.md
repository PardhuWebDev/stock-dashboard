# Stock Intelligence Dashboard

A financial data platform that fetches real NSE stock data, exposes a clean
REST API, and visualizes insights through an interactive dashboard.

---

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite
- **Data:** yfinance, Pandas, NumPy
- **Frontend:** Vanilla JS, Chart.js
- **Server:** Uvicorn

---

## Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/PardhuWebDev/stock-dashboard.git
cd stock-dashboard
```

### 2. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Start the server
```bash
uvicorn main:app --reload --port 8001
```

### 4. Open the dashboard

Navigate to `http://127.0.0.1:8001` in your browser.

On first startup, the application automatically fetches one year of historical
data for INFY, TCS, RELIANCE, WIPRO, and HDFCBANK from yfinance and stores
it locally in a SQLite database.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/companies` | GET | Returns list of all tracked companies |
| `/data/{symbol}` | GET | Returns last 30 days of OHLCV data |
| `/summary/{symbol}` | GET | Returns 52W high, low, avg close, volatility score |
| `/compare?symbol1=INFY&symbol2=TCS` | GET | Normalized % return comparison between two stocks |

Interactive API documentation is available at `http://127.0.0.1:8001/docs`.

---

## Features

- Real NSE stock data fetched via yfinance
- Computed metrics: daily return, 7-day moving average, 52-week high/low
- Custom volatility score per stock
- Interactive price chart with MA7 overlay
- Range filter: 30D, 90D, 180D
- Stock comparison with normalized percentage returns
- Recent sessions table with daily return indicators
- Fully documented REST API via Swagger UI

---

## Custom Metric — Volatility Score
```
Volatility Score = (52W High - 52W Low) / 52W Low * 100
```

Measures the magnitude of price movement over the past year.
A higher score indicates greater price swings and higher risk exposure.

---

## Project Structure
```
stock-dashboard/
├── backend/
│   ├── main.py            FastAPI application and route definitions
│   ├── models.py          SQLAlchemy database model
│   ├── database.py        SQLite engine and session configuration
│   ├── data_loader.py     yfinance data fetch and pandas transformations
│   └── requirements.txt   Python dependencies
├── frontend/
│   └── index.html         Dashboard UI
└── README.md
```

---

## Author

Pardhu — MCA Candidate, SRM Institute of Science and Technology
Stack: Python, FastAPI, JavaScript, Docker, GCP
