from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import psycopg2
import os

# FastAPI app with proper configuration
app = FastAPI(
    title="Expense Tracker API",
    description="API for tracking personal expenses with categories and summaries",
    version="1.0.0",
    servers=[
        {
            "url": "https://expense-fnfhepavd8bnc9eh.eastasia-01.azurewebsites.net",
            "description": "Production server",
        }
    ],
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com", "https://chatgpt.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("Missing DATABASE_URL environment variable")


# Database helper
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# ==================== PYDANTIC MODELS ====================


# Request models
class ExpenseRequest(BaseModel):
    date: str = Field(
        ..., description="Date in YYYY-MM-DD format", example="2025-11-26"
    )
    amount: float = Field(..., description="Expense amount", example=200.00, gt=0)
    category: str = Field(
        ...,
        description="Expense category (Food, Travel, Shopping, Bills, Other)",
        example="Food",
    )
    subcategory: str = Field(
        "", description="Optional subcategory", example="Restaurant"
    )
    note: str = Field("", description="Optional note", example="Lunch with team")


# Response models
class ExpenseData(BaseModel):
    id: int = Field(..., description="Expense ID")
    date: str = Field(..., description="Date of expense")
    amount: float = Field(..., description="Expense amount")
    category: str = Field(..., description="Category")
    subcategory: str = Field(..., description="Subcategory")
    note: str = Field(..., description="Note")


class AddExpenseResponse(BaseModel):
    status: str = Field(..., description="Status of the operation")
    message: str = Field(..., description="Success message")
    data: ExpenseData = Field(..., description="Added expense data")


class ExpenseItem(BaseModel):
    id: int
    date: str
    amount: float
    category: str
    subcategory: str
    note: str


class ListExpensesResponse(BaseModel):
    count: int = Field(..., description="Number of expenses returned")
    expenses: list[ExpenseItem] = Field(..., description="List of expenses")


class CategorySummary(BaseModel):
    category: str = Field(..., description="Category name")
    total: float = Field(..., description="Total amount spent")
    count: int = Field(..., description="Number of expenses")


class PeriodInfo(BaseModel):
    start: str = Field(..., description="Start date")
    end: str = Field(..., description="End date")


class SummaryResponse(BaseModel):
    summary: list[CategorySummary] = Field(..., description="Summary by category")
    total_expenses: int = Field(..., description="Total number of categories")
    grand_total: float = Field(..., description="Total amount across all categories")
    period: PeriodInfo = Field(..., description="Date range for the summary")


# ==================== ENDPOINTS ====================


@app.get("/")
def root():
    return {
        "message": "Expense Tracker API is running!",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/add", response_model=AddExpenseResponse, tags=["Expenses"])
def add_expense_api(expense: ExpenseRequest):
    """
    Add a new expense to the database.

    Categories: Food, Travel, Shopping, Bills, Other
    """
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

                expense_data = ExpenseData(
                    id=row_id,
                    date=expense.date,
                    amount=expense.amount,
                    category=expense.category,
                    subcategory=expense.subcategory,
                    note=expense.note,
                )

                return AddExpenseResponse(
                    status="success",
                    message="Expense added successfully",
                    data=expense_data,
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list", response_model=ListExpensesResponse, tags=["Expenses"])
def list_expenses_api(
    start_date: str = Query(
        ..., description="Start date YYYY-MM-DD", example="2025-11-01"
    ),
    end_date: str = Query(..., description="End date YYYY-MM-DD", example="2025-11-30"),
):
    """
    List all expenses within a date range.
    """
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

                expenses = []
                for r in rows:
                    expenses.append(
                        ExpenseItem(
                            id=r[0],
                            date=str(r[1]),
                            amount=float(r[2]),
                            category=r[3],
                            subcategory=r[4] or "",
                            note=r[5] or "",
                        )
                    )

                return ListExpensesResponse(count=len(expenses), expenses=expenses)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary", response_model=SummaryResponse, tags=["Analytics"])
def summary_api(
    start_date: str = Query(
        ..., description="Start date YYYY-MM-DD", example="2025-11-01"
    ),
    end_date: str = Query(..., description="End date YYYY-MM-DD", example="2025-11-30"),
    category: Optional[str] = Query(
        None, description="Filter by category", example="Food"
    ),
):
    """
    Get expense summary grouped by category.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if category:
                    cur.execute(
                        """
                        SELECT category, SUM(amount) AS total, COUNT(*) AS count
                        FROM expenses
                        WHERE date BETWEEN %s AND %s AND category = %s
                        GROUP BY category;
                        """,
                        (start_date, end_date, category),
                    )
                else:
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
                total_amount = 0
                for r in rows:
                    amount = float(r[1])
                    summary_list.append(
                        CategorySummary(category=r[0], total=amount, count=r[2])
                    )
                    total_amount += amount

                return SummaryResponse(
                    summary=summary_list,
                    total_expenses=len(summary_list),
                    grand_total=total_amount,
                    period=PeriodInfo(start=start_date, end=end_date),
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
