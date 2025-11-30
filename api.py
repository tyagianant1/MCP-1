from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import psycopg2
import os

# FastAPI app with proper configuration
app = FastAPI(
    title="Expense Tracker API",
    description="API for tracking personal expenses with categories and summaries. Now with natural language query support!",
    version="2.0.0",
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


class NaturalQueryRequest(BaseModel):
    question: str = Field(
        ...,
        description="Natural language question about expenses",
        example="How much did I spend on food last month?",
    )
    start_date: Optional[str] = Field(
        None,
        description="Optional start date for context (YYYY-MM-DD)",
        example="2025-11-01",
    )
    end_date: Optional[str] = Field(
        None,
        description="Optional end date for context (YYYY-MM-DD)",
        example="2025-11-30",
    )


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


class NaturalQueryResponse(BaseModel):
    question: str = Field(..., description="Original question asked")
    sql_query: str = Field(..., description="Generated SQL query used")
    results: list[dict] = Field(
        ..., description="Query results as list of dictionaries"
    )
    row_count: int = Field(..., description="Number of rows returned")
    interpretation: str = Field(..., description="Brief explanation of what was found")


# ==================== SQL GENERATION HELPER ====================


def generate_sql_from_question(
    question: str, start_date: Optional[str], end_date: Optional[str]
) -> tuple[str, str]:
    """
    Convert natural language to SQL query using pattern matching.
    Returns (sql_query, interpretation)

    The GPT Action will describe the user's intent, and this function
    translates common patterns into SQL.
    """
    question_lower = question.lower()

    # Default date range
    date_filter = ""
    if start_date and end_date:
        date_filter = f"WHERE date BETWEEN '{start_date}' AND '{end_date}'"
    elif start_date:
        date_filter = f"WHERE date >= '{start_date}'"
    elif end_date:
        date_filter = f"WHERE date <= '{end_date}'"

    # Pattern 1: Total spending (overall or by category)
    if any(word in question_lower for word in ["total", "how much", "sum", "spent"]):
        if any(
            word in question_lower
            for word in ["category", "categories", "by category", "per category"]
        ):
            sql = f"""
            SELECT category, SUM(amount) as total_amount, COUNT(*) as expense_count
            FROM expenses
            {date_filter}
            GROUP BY category
            ORDER BY total_amount DESC
            """
            interpretation = "Showing total spending grouped by category"
        else:
            # Check for specific category
            category_filter = ""
            for cat in ["food", "travel", "shopping", "bills", "other"]:
                if cat in question_lower:
                    cat_condition = f"category ILIKE '%{cat}%'"
                    if date_filter:
                        category_filter = f"{date_filter} AND {cat_condition}"
                    else:
                        category_filter = f"WHERE {cat_condition}"
                    break

            final_filter = category_filter if category_filter else date_filter
            sql = f"""
            SELECT SUM(amount) as total_amount, COUNT(*) as total_expenses
            FROM expenses
            {final_filter}
            """
            interpretation = "Showing total spending amount and number of expenses"

    # Pattern 2: List/Show expenses
    elif any(
        word in question_lower
        for word in ["list", "show", "display", "all", "expenses"]
    ):
        category_filter = ""
        amount_filter = ""

        # Check for category filter
        for cat in ["food", "travel", "shopping", "bills", "other"]:
            if cat in question_lower:
                cat_condition = f"category ILIKE '%{cat}%'"
                category_filter = (
                    f" AND {cat_condition}" if date_filter else f"WHERE {cat_condition}"
                )
                break

        # Check for amount filter (over/above/more than)
        if any(
            word in question_lower
            for word in ["over", "above", "more than", "greater than"]
        ):
            import re

            amount_match = re.search(r"\$?(\d+)", question_lower)
            if amount_match:
                amount = amount_match.group(1)
                amount_condition = f"amount > {amount}"
                if date_filter or category_filter:
                    amount_filter = f" AND {amount_condition}"
                else:
                    amount_filter = f"WHERE {amount_condition}"

        sql = f"""
        SELECT id, date, amount, category, subcategory, note
        FROM expenses
        {date_filter}{category_filter}{amount_filter}
        ORDER BY date DESC, amount DESC
        LIMIT 100
        """
        interpretation = "Showing list of expenses matching your criteria"

    # Pattern 3: Biggest/Highest/Maximum
    elif any(
        word in question_lower
        for word in ["biggest", "highest", "maximum", "most", "largest"]
    ):
        if "category" in question_lower:
            sql = f"""
            SELECT category, SUM(amount) as total_amount, COUNT(*) as expense_count
            FROM expenses
            {date_filter}
            GROUP BY category
            ORDER BY total_amount DESC
            LIMIT 1
            """
            interpretation = "Showing the category with highest spending"
        else:
            sql = f"""
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            {date_filter}
            ORDER BY amount DESC
            LIMIT 10
            """
            interpretation = "Showing the highest individual expenses"

    # Pattern 4: Smallest/Lowest/Minimum
    elif any(
        word in question_lower for word in ["smallest", "lowest", "minimum", "least"]
    ):
        if "category" in question_lower:
            sql = f"""
            SELECT category, SUM(amount) as total_amount, COUNT(*) as expense_count
            FROM expenses
            {date_filter}
            GROUP BY category
            ORDER BY total_amount ASC
            LIMIT 1
            """
            interpretation = "Showing the category with lowest spending"
        else:
            sql = f"""
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            {date_filter}
            ORDER BY amount ASC
            LIMIT 10
            """
            interpretation = "Showing the lowest individual expenses"

    # Pattern 5: Average
    elif any(word in question_lower for word in ["average", "avg", "mean"]):
        if "category" in question_lower:
            sql = f"""
            SELECT category, AVG(amount) as average_amount, COUNT(*) as expense_count
            FROM expenses
            {date_filter}
            GROUP BY category
            ORDER BY average_amount DESC
            """
            interpretation = "Showing average spending per category"
        else:
            sql = f"""
            SELECT AVG(amount) as average_amount, COUNT(*) as total_expenses
            FROM expenses
            {date_filter}
            """
            interpretation = "Showing overall average expense amount"

    # Pattern 6: Count
    elif any(word in question_lower for word in ["count", "number", "how many"]):
        if "category" in question_lower:
            sql = f"""
            SELECT category, COUNT(*) as expense_count, SUM(amount) as total_amount
            FROM expenses
            {date_filter}
            GROUP BY category
            ORDER BY expense_count DESC
            """
            interpretation = "Showing count of expenses per category"
        else:
            sql = f"""
            SELECT COUNT(*) as total_count
            FROM expenses
            {date_filter}
            """
            interpretation = "Showing total count of expenses"

    # Default: Return recent expenses
    else:
        sql = f"""
        SELECT id, date, amount, category, subcategory, note
        FROM expenses
        {date_filter}
        ORDER BY date DESC
        LIMIT 50
        """
        interpretation = "Showing recent expenses (default view)"

    return sql.strip(), interpretation


# ==================== ENDPOINTS ====================


@app.get("/")
def root():
    return {
        "message": "Expense Tracker API is running!",
        "version": "2.0.0",
        "docs": "/docs",
        "new_features": ["Natural language query support via /query endpoint"],
    }


@app.get("/health")
def health():
    return {"status": "healthy", "database": "connected"}


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


@app.post("/query", response_model=NaturalQueryResponse, tags=["AI Query"])
def natural_language_query(request: NaturalQueryRequest):
    """
    Ask questions about expenses in natural language.

    Examples: "How much did I spend on food?", "Show travel expenses over $100", "What's my biggest category?"

    Database: expenses table with id, date, amount, category, subcategory, note
    Categories: Food, Travel, Shopping, Bills, Other
    """
    # """
    # 🤖 Execute a natural language query about expenses.

    # This endpoint allows you to ask questions in plain English and get SQL-powered answers.

    # **Example Questions:**
    # - "How much did I spend on food last month?"
    # - "Show me all travel expenses over $100"
    # - "What's my biggest expense category?"
    # - "List all shopping expenses from last week"
    # - "What's the average amount I spend on bills?"
    # - "How many expenses do I have in November?"
    # - "Show me my smallest expenses"

    # **Database Schema:**
    # - Table: expenses
    # - Columns: id, date, amount, category, subcategory, note
    # - Categories: Food, Travel, Shopping, Bills, Other

    # **Tips:**
    # - Provide start_date and end_date for better context
    # - Be specific about categories, amounts, or time periods
    # - The system understands common query patterns like "total", "list", "show", "average", etc.
    # """
    try:
        # Generate SQL from natural language
        sql_query, interpretation = generate_sql_from_question(
            request.question, request.start_date, request.end_date
        )

        # Execute the query
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query)
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]

                # Convert to list of dicts
                results = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        value = row[i]
                        # Convert Decimal and date to string for JSON serialization
                        if hasattr(value, "isoformat"):
                            value = value.isoformat()
                        elif hasattr(value, "__float__"):
                            value = float(value)
                        row_dict[col] = value
                    results.append(row_dict)

                return NaturalQueryResponse(
                    question=request.question,
                    sql_query=sql_query,
                    results=results,
                    row_count=len(results),
                    interpretation=interpretation,
                )
    except psycopg2.Error as e:
        raise HTTPException(status_code=400, detail=f"Database query error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
