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

# ================= TELEGRAM =================

TELEGRAM_TOKEN = "8003975040:AAGoh-EIOjs9-0weN68ISUHZvDvjnI_mql8"
TELEGRAM_CHAT_ID = "6352149388"

def send_telegram(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=5
        )
    except Exception as e:
        print("Telegram error:", e)

# ================= MODEL =================

class Booking(BaseModel):
    client_name: str
    phone: str
    service: str
    datetime: datetime

# ================= PAGES =================

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

# ================= AUTH =================

@app.post("/login")
async def login(request: Request):
    form = await request.form()
    if form.get("password") == ADMIN_PASSWORD:
        request.session["admin"] = True
        return {"ok": True}
    return {"ok": False}

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}

# ================= CREATE BOOKING =================

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
    db.refresh(new)

    # Зберігаємо дані ДО db.close()
    name, phone, service, dt = new.client_name, new.phone, new.service, new.datetime
    db.close()

    send_telegram(
        f"🆕 НОВИЙ ЗАПИС!\n\n👤 {name}\n📞 {phone}\n✂️ {service}\n🕒 {dt}"
    )

    return {"ok": True}

# ================= ADMIN BOOKINGS =================

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

    # ⭐ ЗБЕРІГАЄМО ДАНІ ДО commit
    name = booking.client_name
    phone = booking.phone
    service = booking.service
    dt = booking.datetime

    booking.status = "confirmed"
    db.commit()
    db.close()

    send_telegram(
        f"✅ ЗАПИС ПІДТВЕРДЖЕНО\n\n"
        f"👤 {name}\n📞 {phone}\n✂️ {service}\n🕒 {dt}"
    )

    return {"ok": True}

@app.put("/booking/{id}/cancel")
def cancel_booking(id: int, request: Request):
    if not request.session.get("admin"):
        raise HTTPException(403)

    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == id).first()

    # ⭐ ЗБЕРІГАЄМО ДАНІ ДО commit
    name = booking.client_name
    phone = booking.phone
    service = booking.service
    dt = booking.datetime

    booking.status = "cancelled"
    db.commit()
    db.close()

    send_telegram(
        f"❌ ЗАПИС СКАСОВАНО\n\n"
        f"👤 {name}\n📞 {phone}\n✂️ {service}\n🕒 {dt}"
    )

    return {"ok": True}

# ================= REMINDERS =================

def send_reminders():
    db = SessionLocal()
    tomorrow = datetime.now() + timedelta(days=1)

    bookings = db.query(Appointment).filter(
        Appointment.datetime >= tomorrow.replace(hour=0, minute=0),
        Appointment.datetime <= tomorrow.replace(hour=23, minute=59),
        Appointment.status == "confirmed"
    ).all()

    for b in bookings:
        send_telegram(f"⏰ НАГАДУВАННЯ\n\nЗавтра запис:\n👤 {b.client_name}\n✂️ {b.service}\n🕒 {b.datetime}")

    db.close()

@app.on_event("startup")
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_reminders, "interval", hours=24)
    scheduler.start()