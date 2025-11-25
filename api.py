from fastapi import FastAPI
from main import add_expense, list_expenses, summary

app = FastAPI()

@app.post("/add")
def add_api(payload: dict):
    return add_expense(**payload)

@app.get("/list")
def list_api(start_date: str, end_date: str):
    return list_expenses(start_date, end_date)

@app.get("/summary")
def summary_api(start_date: str, end_date: str, category: str = None):
    return summarize(start_date, end_date, category)
