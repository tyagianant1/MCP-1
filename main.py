from fastmcp import FastMCP
import psycopg2
import os
import json
import pathlib

mcp = FastMCP("ExpenseTracker")

# Load from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("❌ Missing environment variable DATABASE_URL")


# ---------------------------------------------------------
# Database Connection Helper (psycopg2)
# ---------------------------------------------------------
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# ---------------------------------------------------------
# Add Expense
# ---------------------------------------------------------
@mcp.tool()
def add_expense(date: str, amount: float, category: str,
                subcategory: str = "", note: str = ""):
    """Add a new expense into PostgreSQL."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO expenses (date, amount, category, subcategory, note)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (date, amount, category, subcategory, note)
                )
                row_id = cur.fetchone()[0]
                return {"status": "success", "id": row_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------
# List Expenses
# ---------------------------------------------------------
@mcp.tool()
def list_expenses(start_date: str, end_date: str):
    """List all expenses in a date range."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, date, amount, category, subcategory, note
                    FROM expenses
                    WHERE date BETWEEN %s AND %s
                    ORDER BY date DESC, id DESC;
                    """,
                    (start_date, end_date)
                )
                rows = cur.fetchall()
                cols = [desc[0] for desc in cur.description]

        return [dict(zip(cols, row)) for row in rows]

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------
# Summarize
# ---------------------------------------------------------
@mcp.tool()
def summarize(start_date: str, end_date: str, category: str = None):
    """Summarize expenses by category."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if category:
                    cur.execute(
                        """
                        SELECT category, SUM(amount) AS total, COUNT(*) AS count
                        FROM expenses
                        WHERE date BETWEEN %s AND %s
                          AND category = %s
                        GROUP BY category;
                        """,
                        (start_date, end_date, category)
                    )
                else:
                    cur.execute(
                        """
                        SELECT category, SUM(amount) AS total, COUNT(*) AS count
                        FROM expenses
                        WHERE date BETWEEN %s AND %s
                        GROUP BY category;
                        """,
                        (start_date, end_date)
                    )

                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]

        return [dict(zip(cols, r)) for r in rows]

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------
# Categories Resource
# ---------------------------------------------------------
CATEGORIES_FILE = pathlib.Path(__file__).parent / "categories.json"

@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    try:
        if CATEGORIES_FILE.exists():
            return CATEGORIES_FILE.read_text()
    except:
        pass

    return json.dumps({
        "categories": ["Food", "Travel", "Shopping", "Bills", "Other"]
    })


# ---------------------------------------------------------
# Run MCP Server
# ---------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
