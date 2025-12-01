from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import psycopg2
import os

# ==================== FASTAPI APP ====================

app = FastAPI(
    title="Expense Tracker API",
    description="Knowledge-based AI Expense Tracker",
    version="3.0.0",
    servers=[
        {
            "url": "https://expense-fnfhepavd8bnc9eh.eastasia-01.azurewebsites.net",
            "description": "Production",
        }
    ],
)

# ==================== CORS ====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com", "https://chatgpt.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATABASE ====================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("Missing DATABASE_URL")


def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# ==================== SQL SAFETY ====================


def validate_sql(sql: str):
    sql_upper = sql.strip().upper()

    if not sql_upper.startswith("SELECT"):
        raise ValueError("Only SELECT allowed")

    blocked = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "CREATE"]
    for word in blocked:
        if word in sql_upper:
            raise ValueError(f"Blocked keyword: {word}")

    if "LIMIT" not in sql_upper:
        raise ValueError("LIMIT clause required for safety")


# ==================== MODELS ====================


class ExpenseRequest(BaseModel):
    date: str = Field(example="2025-11-26")
    amount: float = Field(gt=0, example=200.00)
    category: str = Field(example="Food")
    subcategory: str = Field("", example="Restaurant")
    note: str = Field("", example="Lunch")


class NaturalQueryRequest(BaseModel):
    question: str = Field(example="Sum of expenses in Nov 2025 with value > 1000")
    sql_query: str = Field(
        example="SELECT SUM(amount) FROM expenses WHERE date BETWEEN '2025-11-01' AND '2025-11-30' AND amount > 1000 LIMIT 100"
    )
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class NaturalQueryResponse(BaseModel):
    question: str
    sql_query: str
    results: list[dict]
    row_count: int
    interpretation: str


class ExpenseData(BaseModel):
    id: int
    date: str
    amount: float
    category: str
    subcategory: str
    note: str


class AddExpenseResponse(BaseModel):
    status: str
    message: str
    data: ExpenseData


class ExpenseItem(BaseModel):
    id: int
    date: str
    amount: float
    category: str
    subcategory: str
    note: str


class ListExpensesResponse(BaseModel):
    count: int
    expenses: list[ExpenseItem]


class CategorySummary(BaseModel):
    category: str
    total: float
    count: int


class PeriodInfo(BaseModel):
    start: str
    end: str


class SummaryResponse(BaseModel):
    summary: list[CategorySummary]
    total_expenses: int
    grand_total: float
    period: PeriodInfo


# ==================== ENDPOINTS ====================


@app.get("/")
def root():
    return {
        "message": "Expense Tracker API v3 (knowledge-based AI mode)",
        "features": [
            "GPT generates SQL from knowledge base",
            "Backend validates and executes SQL only",
            "SQL is not hardcoded",
        ],
    }


@app.post("/add", response_model=AddExpenseResponse)
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
                row_id = cur.fetchone()[0]

                return AddExpenseResponse(
                    status="success",
                    message="Expense added",
                    data=ExpenseData(
                        id=row_id,
                        date=expense.date,
                        amount=expense.amount,
                        category=expense.category,
                        subcategory=expense.subcategory,
                        note=expense.note,
                    ),
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list", response_model=ListExpensesResponse)
def list_expenses(start_date: str = Query(...), end_date: str = Query(...)):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, date, amount, category, subcategory, note
                    FROM expenses
                    WHERE date BETWEEN %s AND %s
                    ORDER BY date DESC;
                    """,
                    (start_date, end_date),
                )
                rows = cur.fetchall()

                items = [
                    ExpenseItem(
                        id=r[0],
                        date=str(r[1]),
                        amount=float(r[2]),
                        category=r[3],
                        subcategory=r[4] or "",
                        note=r[5] or "",
                    )
                    for r in rows
                ]

                return ListExpensesResponse(count=len(items), expenses=items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary", response_model=SummaryResponse)
def summary(start_date: str = Query(...), end_date: str = Query(...)):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT category, SUM(amount) AS total, COUNT(*) AS count
                    FROM expenses
                    WHERE date BETWEEN %s AND %s
                    GROUP BY category
                    ORDER BY total DESC;
                    """,
                    (start_date, end_date),
                )

                rows = cur.fetchall()

                summary_list = []
                total = 0
                for r in rows:
                    summary_list.append(
                        CategorySummary(category=r[0], total=float(r[1]), count=r[2])
                    )
                    total += float(r[1])

                return SummaryResponse(
                    summary=summary_list,
                    total_expenses=len(summary_list),
                    grand_total=total,
                    period=PeriodInfo(start=start_date, end=end_date),
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=NaturalQueryResponse)
def execute_query(request: NaturalQueryRequest):
    try:
        validate_sql(request.sql_query)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '8s'")
                cur.execute(request.sql_query)
                rows = cur.fetchall()
                columns = [col.name for col in cur.description]

                results = []
                for row in rows:
                    obj = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if hasattr(val, "isoformat"):
                            val = val.isoformat()
                        elif hasattr(val, "__float__"):
                            val = float(val)
                        obj[col] = val
                    results.append(obj)

        return NaturalQueryResponse(
            question=request.question,
            sql_query=request.sql_query,
            results=results,
            row_count=len(results),
            interpretation=f"Query executed successfully. {len(results)} rows returned.",
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== RUN ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
