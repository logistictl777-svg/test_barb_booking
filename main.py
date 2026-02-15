from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from datetime import datetime

from database import SessionLocal, engine
from models import Appointment

app = FastAPI()

# 🔥 ОБОВʼЯЗКОВИЙ ПОРЯДОК
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key="secret")

Appointment.metadata.create_all(bind=engine)

ADMIN_PASSWORD = "1234"

# ---------- PAGES ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/")
    return templates.TemplateResponse("admin.html", {"request": request})

# ---------- AUTH ----------
@app.post("/login")
def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["admin"] = True
        return {"status":"ok"}
    return {"status":"error"}

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status":"ok"}

# ---------- API ----------
class Booking(BaseModel):
    client_name:str
    phone:str
    service:str
    datetime:datetime

@app.post("/book")
def book(data:Booking):
    db=SessionLocal()
    exists=db.query(Appointment).filter(Appointment.datetime==data.datetime).first()
    if exists:
        raise HTTPException(400,"Time busy")

    booking=Appointment(**data.dict(),status="confirmed")
    db.add(booking)
    db.commit()
    db.close()
    return {"status":"ok"}

@app.get("/available-times")
def times(date:str):
    return [f"{h:02d}:00" for h in range(10,19)]