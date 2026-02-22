"""Database connection utilities for the Warp Data Analyst."""

import os
import mysql.connector
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Create and return a MySQL database connection."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        connect_timeout=30
    )


def execute_query(sql: str) -> pd.DataFrame:
    """Execute a SQL query and return results as a DataFrame."""
    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn)
        return df
    finally:
        conn.close()


def test_connection() -> bool:
    """Test the database connection."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    # Quick test
    if test_connection():
        print("✅ Database connection successful!")
    else:
        print("❌ Database connection failed!")

