from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import requests

from database import SessionLocal, engine
from models import Appointment

# =====================================================
# 🚀 APP INIT
# =====================================================

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="super-secret-key",
    https_only=True,
    same_site="none"
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

Appointment.metadata.create_all(bind=engine)

ADMIN_PASSWORD = "1234"

# =====================================================
# 🤖 TELEGRAM
# =====================================================

TELEGRAM_TOKEN = "8003975040:AAGoh-EIOjs9-0weN68ISUHZvDvjnI_mql8"
TELEGRAM_CHAT_ID = "6352149388"

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})

# =====================================================
# 📦 MODEL
# =====================================================

class Booking(BaseModel):
    client_name: str
    phone: str
    service: str
    datetime: datetime

# =====================================================
# 🌐 PAGES
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/login")
    return templates.TemplateResponse("admin.html", {"request": request})

# =====================================================
# 🔐 AUTH
# =====================================================

@app.post("/login")
async def login(request: Request):
    form = await request.form()
    password = form.get("password")

    if password == ADMIN_PASSWORD:
        request.session["admin"] = True
        return {"ok": True}

    return {"ok": False}

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}

# =====================================================
# ✂️ CREATE BOOKING
# =====================================================

@app.post("/book")
def create_booking(booking: Booking):
    db = SessionLocal()

    exists = db.query(Appointment).filter(
        Appointment.datetime == booking.datetime
    ).first()

    if exists:
        db.close()
        raise HTTPException(400, "Цей час вже зайнятий 😢")

    new = Appointment(
        client_name=booking.client_name,
        phone=booking.phone,
        service=booking.service,
        datetime=booking.datetime,
        status="pending"
    )

    db.add(new)
    db.commit()
    db.refresh(new)   # ⭐ ДУЖЕ ВАЖЛИВО

    # ⭐ TELEGRAM В TRY щоб не ламав API
    try:
        send_telegram(
            f"🆕 НОВИЙ ЗАПИС!\n\n"
            f"👤 {new.client_name}\n"
            f"📞 {new.phone}\n"
            f"✂️ {new.service}\n"
            f"🕒 {new.datetime}\n"
            f"Статус: PENDING"
        )
    except Exception as e:
        print("Telegram error:", e)

    db.close()
    return {"ok": True}

# =====================================================
# 📅 AVAILABLE TIMES
# =====================================================

@app.get("/available-times")
def available_times(date: str):
    db = SessionLocal()

    WORK_START = 10
    WORK_END = 19

    selected_date = datetime.strptime(date, "%Y-%m-%d")
    start = selected_date.replace(hour=0, minute=0, second=0)
    end = selected_date.replace(hour=23, minute=59, second=59)

    bookings = db.query(Appointment).filter(
        Appointment.datetime >= start,
        Appointment.datetime <= end,
        Appointment.status != "cancelled"
    ).all()

    busy = [b.datetime.strftime("%H:00") for b in bookings]

    free = []
    for hour in range(WORK_START, WORK_END):
        slot = f"{hour:02d}:00"
        if slot not in busy:
            free.append(slot)

    db.close()
    return free

# =====================================================
# 👨‍💼 ADMIN BOOKINGS
# =====================================================

@app.get("/admin/bookings")
def admin_bookings(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(403)

    db = SessionLocal()
    data = db.query(Appointment).order_by(Appointment.datetime).all()
    db.close()
    return data

@app.put("/booking/{id}/confirm")
def confirm_booking(id: int, request: Request):
    if not request.session.get("admin"):
        raise HTTPException(403)

    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == id).first()

    booking.status = "confirmed"
    db.commit()
    db.close()

    send_telegram(
        f"✅ ЗАПИС ПІДТВЕРДЖЕНО\n\n"
        f"👤 {booking.client_name}\n"
        f"📞 {booking.phone}\n"
        f"✂️ {booking.service}\n"
        f"🕒 {booking.datetime}"
    )

    return {"ok": True}

@app.put("/booking/{id}/cancel")
def cancel_booking(id: int, request: Request):
    if not request.session.get("admin"):
        raise HTTPException(403)

    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == id).first()

    booking.status = "cancelled"
    db.commit()
    db.close()

    send_telegram(
        f"❌ ЗАПИС СКАСОВАНО\n\n"
        f"👤 {booking.client_name}\n"
        f"📞 {booking.phone}\n"
        f"✂️ {booking.service}\n"
        f"🕒 {booking.datetime}"
    )

    return {"ok": True}

# =====================================================
# ⏰ REMINDERS
# =====================================================

def send_reminders():
    db = SessionLocal()

    tomorrow = datetime.now() + timedelta(days=1)
    start = tomorrow.replace(hour=0, minute=0, second=0)
    end = tomorrow.replace(hour=23, minute=59, second=59)

    bookings = db.query(Appointment).filter(
        Appointment.datetime >= start,
        Appointment.datetime <= end,
        Appointment.status == "confirmed"
    ).all()

    for b in bookings:
        send_telegram(
            f"⏰ НАГАДУВАННЯ\n\n"
            f"Завтра запис:\n"
            f"👤 {b.client_name}\n"
            f"✂️ {b.service}\n"
            f"🕒 {b.datetime}"
        )

    db.close()

@app.on_event("startup")
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_reminders, "interval", hours=24)
    scheduler.start()