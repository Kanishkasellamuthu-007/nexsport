"""Runs the NexSport Flask app locally.

Usage (from the project root):
    python run.py
"""
from backend.app import app
from backend.config import config

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
