from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg
import os

# ---------------------------------------------------------
# FASTAPI APP
# ---------------------------------------------------------
app = FastAPI(title="Expense Tracker API", version="0.1.0")

# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("❌ ERROR: DATABASE_URL not found. Set it in Render environment.")

def get_conn():
    return psycopg.connect(DATABASE_URL, autocommit=True)

# ---------------------------------------------------------
# REQUEST BODY MODEL
# ---------------------------------------------------------
class Expense(BaseModel):
    date: str
    amount: float
    category: str
    subcategory: str
    note: str


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@app.get("/")
def root():
    return {"message": "Expense Tracker API is running!"}

# -------------------- ADD EXPENSE ------------------------
@app.post("/add")
def add_expense(expense: Expense):
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO expenses (date, amount, category, subcategory, note)
            VALUES (%s, %s, %s, %s, %s)
        """, (expense.date, expense.amount, expense.category, expense.subcategory, expense.note))

        return {
            "status": "success",
            "message": "Expense added successfully",
            "data": expense.dict()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- LIST EXPENSES ------------------------
@app.get("/list")
def list_expenses(start_date: str, end_date: str):

    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN %s AND %s
            ORDER BY date ASC
        """, (start_date, end_date))

        rows = cur.fetchall()

        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "date": r[1],
                "amount": float(r[2]),
                "category": r[3],
                "subcategory": r[4],
                "note": r[5]
            })

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- SUMMARY ------------------------
@app.get("/summary")
def summary(start_date: str, end_date: str, category: str = None):
    try:
        conn = get_conn()
        cur = conn.cursor()

        if category:
            cur.execute("""
                SELECT category, SUM(amount)
                FROM expenses
                WHERE date BETWEEN %s AND %s AND category = %s
                GROUP BY category
            """, (start_date, end_date, category))
        else:
            cur.execute("""
                SELECT category, SUM(amount)
                FROM expenses
                WHERE date BETWEEN %s AND %s
                GROUP BY category
            """, (start_date, end_date))

        rows = cur.fetchall()

        summary_list = [{"category": r[0], "total": float(r[1])} for r in rows]

        return {"summary": summary_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
