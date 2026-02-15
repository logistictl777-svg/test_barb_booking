from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from pydantic import BaseModel
import requests

from database import SessionLocal, engine
from models import Appointment

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key="secret")

Appointment.metadata.create_all(bind=engine)

ADMIN_PASSWORD="1234"
TELEGRAM_TOKEN="PUT_YOUR_TOKEN"
TELEGRAM_CHAT_ID="PUT_CHAT_ID"

def send_telegram(text):
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url,data={"chat_id":TELEGRAM_CHAT_ID,"text":text})

# ---------- REMINDERS ----------
def send_reminders():
    db=SessionLocal()
    tomorrow=datetime.now()+timedelta(days=1)
    start=tomorrow.replace(hour=0,minute=0,second=0)
    end=tomorrow.replace(hour=23,minute=59,second=59)

    bookings=db.query(Appointment).filter(
        Appointment.datetime>=start,
        Appointment.datetime<=end,
        Appointment.status=="confirmed"
    ).all()

    for b in bookings:
        send_telegram(f"⏰ Завтра запис\n{b.client_name}\n{b.service}\n{b.datetime}")

    db.close()

@app.on_event("startup")
def start_scheduler():
    scheduler=BackgroundScheduler()
    scheduler.add_job(send_reminders,"interval",hours=12)
    scheduler.start()

# ---------- PAGES ----------
@app.get("/",response_class=HTMLResponse)
def home(request:Request):
    return templates.TemplateResponse("index.html",{"request":request})

@app.get("/admin",response_class=HTMLResponse)
def admin(request:Request):
    if not request.session.get("admin"):
        return RedirectResponse("/")
    return templates.TemplateResponse("admin.html",{"request":request})

# ---------- AUTH ----------
@app.post("/login")
def login(request:Request,password:str=Form(...)):
    if password==ADMIN_PASSWORD:
        request.session["admin"]=True
        return {"ok":True}
    return {"ok":False}

@app.get("/logout")
def logout(request:Request):
    request.session.clear()
    return {"ok":True}

# ---------- BOOKING ----------
class Booking(BaseModel):
    client_name:str
    phone:str
    service:str
    datetime:datetime

@app.post("/book")
def book(data:Booking):
    db=SessionLocal()
    exists=db.query(Appointment).filter(Appointment.datetime==data.datetime).first()
    if exists: raise HTTPException(400,"Час зайнятий")

    booking=Appointment(**data.dict(),status="pending")
    db.add(booking)
    db.commit()
    db.refresh(booking)

    send_telegram(f"🆕 Новий запис\n{booking.client_name}\n{booking.service}\n{booking.datetime}")
    db.close()
    return {"ok":True}

@app.get("/admin/bookings")
def bookings(request:Request):
    if not request.session.get("admin"): raise HTTPException(403)
    db=SessionLocal()
    data=db.query(Appointment).order_by(Appointment.datetime).all()
    db.close()
    return data

@app.put("/booking/{id}/confirm")
def confirm(id:int,request:Request):
    if not request.session.get("admin"): raise HTTPException(403)
    db=SessionLocal()
    b=db.query(Appointment).get(id)
    b.status="confirmed"
    db.commit()
    send_telegram(f"✅ Запис підтверджено\n{b.client_name}\n{b.datetime}")
    db.close()
    return {"ok":True}

@app.put("/booking/{id}/cancel")
def cancel(id:int,request:Request):
    if not request.session.get("admin"): raise HTTPException(403)
    db=SessionLocal()
    b=db.query(Appointment).get(id)
    b.status="cancelled"
    db.commit()
    send_telegram(f"❌ Запис скасовано\n{b.client_name}\n{b.datetime}")
    db.close()
    return {"ok":True}

@app.get("/available-times")
def times(date:str):
    db=SessionLocal()
    day=datetime.strptime(date,"%Y-%m-%d")
    bookings=db.query(Appointment).filter(Appointment.datetime>=day).all()
    busy=[b.datetime.strftime("%H:00") for b in bookings]
    db.close()
    return [f"{h:02d}:00" for h in range(10,19) if f"{h:02d}:00" not in busy]