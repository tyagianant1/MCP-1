from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
import os

app = FastAPI(title="Expense Tracker API")

# -----------------------------
# CORS (Required for ChatGPT)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Allow all (safe for your usage)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Database Connection
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("❌ DATABASE_URL not found")

def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# -----------------------------
# Models
# -----------------------------
class ExpenseRequest(BaseModel):
    date: str
    amount: float
    category: str
    subcategory: Optional[str] = ""
    note: Optional[str] = ""


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return {"message": "Expense Tracker API is running!"}


# ADD EXPENSE
@app.post("/add")
def add_expense(expense: ExpenseRequest):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO expenses (date, amount, category, subcategory, note)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        expense.date,
                        expense.amount,
                        expense.category,
                        expense.subcategory,
                        expense.note,
                    ),
                )
                new_id = cur.fetchone()[0]

        return {
            "status": "success",
            "message": "Expense added successfully",
            "data": {
                "id": new_id,
                "date": expense.date,
                "amount": expense.amount,
                "category": expense.category,
                "subcategory": expense.subcategory,
                "note": expense.note,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# LIST EXPENSES
@app.get("/list")
def list_expenses(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
):
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
                    (start_date, end_date),
                )
                rows = cur.fetchall()

        result = [
            {
                "id": r[0],
                "date": str(r[1]),
                "amount": float(r[2]),
                "category": r[3],
                "subcategory": r[4],
                "note": r[5],
            }
            for r in rows
        ]

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# SUMMARY
@app.get("/summary")
def summary(
    start_date: str = Query(...),
    end_date: str = Query(...),
    category: Optional[str] = Query(None),
):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if category:
                    cur.execute(
                        """
                        SELECT category, SUM(amount), COUNT(*)
                        FROM expenses
                        WHERE date BETWEEN %s AND %s AND category=%s
                        GROUP BY category;
                        """,
                        (start_date, end_date, category),
                    )
                else:
                    cur.execute(
                        """
                        SELECT category, SUM(amount), COUNT(*)
                        FROM expenses
                        WHERE date BETWEEN %s AND %s
                        GROUP BY category;
                        """,
                        (start_date, end_date),
                    )

                rows = cur.fetchall()

        summary_data = [
            {"category": r[0], "total": float(r[1]), "count": r[2]} for r in rows
        ]

        return {"summary": summary_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------
# LOCAL RUN
# -----------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
