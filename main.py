from apscheduler.schedulers.background import BackgroundScheduler
from datetime import timedelta, datetime
import requests

from fastapi import Request, FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from database import SessionLocal, engine
from models import Appointment

# =====================================================
# 🚀 APP INIT (ПРАВИЛЬНИЙ ПОРЯДОК)
# =====================================================

app = FastAPI()

# 🔥 1. STATIC ПОВИНЕН БУТИ ПЕРШИМ
app.mount("/static", StaticFiles(directory="static"), name="static")

# 🔥 2. TEMPLATES ПІСЛЯ STATIC
templates = Jinja2Templates(directory="templates")

# 🔥 3. СЕСІЇ ПІСЛЯ ВСЬОГО
app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

# створюємо таблиці
Appointment.metadata.create_all(bind=engine)

ADMIN_PASSWORD = "1234"
# =====================================================
# 📲 TELEGRAM
# =====================================================
TELEGRAM_TOKEN = "TOKEN"
TELEGRAM_CHAT_ID = "CHAT_ID"

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})

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

    for booking in bookings:
        send_telegram(
            f"⏰ Нагадування!\n\n"
            f"👤 {booking.client_name}\n"
            f"✂️ {booking.service}\n"
            f"🕐 {booking.datetime}"
        )

    db.close()

@app.on_event("startup")
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_reminders, "interval", minutes=60)
    scheduler.start()

# =====================================================
# 📄 PAGES
# =====================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/")
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/")
    return templates.TemplateResponse("calendar.html", {"request": request})

# =====================================================
# 🔐 AUTH
# =====================================================
@app.post("/login")
def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["admin"] = True
        return {"status": "ok"}
    return {"status": "error"}

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}

@app.get("/check-admin")
def check_admin(request: Request):
    return {"admin": request.session.get("admin", False)}

# =====================================================
# 📅 BOOKING API
# =====================================================
class Booking(BaseModel):
    client_name: str
    phone: str
    service: str
    datetime: datetime

@app.post("/book")
def create_booking(booking: Booking):
    db = SessionLocal()

    existing = db.query(Appointment).filter(
        Appointment.datetime == booking.datetime
    ).first()

    if existing:
        db.close()
        raise HTTPException(400, "Цей час вже зайнятий 😢")

    new_appointment = Appointment(
        client_name=booking.client_name,
        phone=booking.phone,
        service=booking.service,
        datetime=booking.datetime,
        status="pending"
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    send_telegram(
        f"📝 Новий запис\n"
        f"{new_appointment.client_name}\n"
        f"{new_appointment.service}\n"
        f"{new_appointment.datetime}"
    )

    db.close()
    return {"status": "ok"}

@app.get("/bookings")
def get_bookings():
    db = SessionLocal()
    bookings = db.query(Appointment).all()
    db.close()
    return bookings

@app.delete("/booking/{booking_id}")
def delete_booking(booking_id: int):
    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == booking_id).first()
    if not booking:
        db.close()
        raise HTTPException(404)
    db.delete(booking)
    db.commit()
    db.close()
    return {"status": "deleted"}

# =====================================================
# 🕒 AVAILABLE TIME SLOTS
# =====================================================
@app.get("/available-times")
def available_times(date: str):
    db = SessionLocal()

    WORK_START, WORK_END = 10, 19
    selected_date = datetime.strptime(date, "%Y-%m-%d")

    start_day = selected_date.replace(hour=0, minute=0, second=0)
    end_day = selected_date.replace(hour=23, minute=59, second=59)

    bookings = db.query(Appointment).filter(
        Appointment.datetime >= start_day,
        Appointment.datetime <= end_day,
        Appointment.status != "cancelled"
    ).all()

    busy = [b.datetime.strftime("%H:00") for b in bookings]

    free = [f"{h:02d}:00" for h in range(WORK_START, WORK_END) if f"{h:02d}:00" not in busy]

    db.close()
    return free