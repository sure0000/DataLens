"""FastAPI app without table lineage."""
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id, "name": "demo"}
