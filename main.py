from apscheduler.schedulers.background import BackgroundScheduler
from datetime import timedelta

import requests
TELEGRAM_TOKEN = "8003975040:AAGoh-EIOjs9-0weN68ISUHZvDvjnI_mql8"
TELEGRAM_CHAT_ID = "6352149388"

# 📲 TELEGRAM SEND FUNCTION
def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    requests.post(url, data=data)


# ⏰ REMINDER FUNCTION
def send_reminders():
    db = SessionLocal()

    tomorrow = datetime.now() + timedelta(days=1)
    start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    end = tomorrow.replace(hour=23, minute=59, second=59)

    bookings = db.query(Appointment).filter(
        Appointment.datetime >= start,
        Appointment.datetime <= end,
        Appointment.status == "confirmed"
    ).all()

    for booking in bookings:
        send_telegram(
            f"⏰ Нагадування!\n\n"
            f"Завтра у вас запис:\n"
            f"👤 {booking.client_name}\n"
            f"✂️ {booking.service}\n"
            f"🕐 {booking.datetime}"
        )

    db.close()
ADMIN_PASSWORD = "1234"

from fastapi import Request, FastAPI, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from datetime import datetime

from database import SessionLocal, engine
from models import Appointment

app = FastAPI()

@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/")
    return templates.TemplateResponse("calendar.html", {"request": request})

# SESSION middleware
app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

# templates
app.mount("/templates", StaticFiles(directory="templates"), name="templates")
templates = Jinja2Templates(directory="templates")

# створюємо таблиці
Appointment.metadata.create_all(bind=engine)

# -----------------------------
# Pydantic модель запиту
# -----------------------------
class Booking(BaseModel):
    client_name: str
    phone: str
    service: str
    datetime: datetime

# -----------------------------
# HOME PAGE
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# -----------------------------
# LOGIN / ADMIN AUTH
# -----------------------------
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

# -----------------------------
# ADMIN PAGE
# -----------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/")
    return templates.TemplateResponse("admin.html", {"request": request})

# -----------------------------
# ➕ CREATE BOOKING (CLIENT)
# -----------------------------
@app.post("/book")
def create_booking(booking: Booking):
    db = SessionLocal()

    # перевірка чи зайнятий час
    existing_booking = db.query(Appointment).filter(
        Appointment.datetime == booking.datetime
    ).first()

    if existing_booking:
        db.close()
        raise HTTPException(status_code=400, detail="Цей час вже зайнятий 😢")

    # створюємо запис
    new_appointment = Appointment(
        client_name=booking.client_name,
        phone=booking.phone,
        service=booking.service,
        datetime=booking.datetime,
        status="pending"   # ⭐ важливо
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    # 📲 TELEGRAM ПОВІДОМЛЕННЯ КЛІЄНТУ
    send_telegram(
        f"📝 Ви успішно записались до барбера!\n\n"
        f"👤 {new_appointment.client_name}\n"
        f"📞 {new_appointment.phone}\n"
        f"✂️ {new_appointment.service}\n"
        f"🕐 {new_appointment.datetime}\n\n"
        f"⏳ Очікуйте підтвердження адміністратора"
    )

    db.close()
    return {"status": "Запис успішно створено"}

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    db.close()

    return {"status": "Запис створено ✅"}

# -----------------------------
# 📋 CLIENT BOOKINGS
# -----------------------------
@app.get("/bookings")
def get_bookings():
    db = SessionLocal()
    bookings = db.query(Appointment).all()
    db.close()
    return bookings

# -----------------------------
# ❌ DELETE BOOKING
# -----------------------------
@app.delete("/booking/{booking_id}")
def delete_booking(booking_id: int):
    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == booking_id).first()

    if not booking:
        db.close()
        raise HTTPException(status_code=404, detail="Booking not found")

    db.delete(booking)
    db.commit()
    db.close()

    return {"status": "deleted"}

# -----------------------------
# ✏ UPDATE BOOKING
# -----------------------------
@app.put("/booking/{booking_id}")
def update_booking(booking_id: int, updated_booking: Booking):
    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == booking_id).first()

    if not booking:
        db.close()
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.client_name = updated_booking.client_name
    booking.phone = updated_booking.phone
    booking.service = updated_booking.service
    booking.datetime = updated_booking.datetime

    db.commit()
    db.close()

    return {"status": "updated"}

# =====================================================
# ⭐ ADMIN ENDPOINTS
# =====================================================

# 📋 ADMIN GET BOOKINGS
@app.get("/admin/bookings")
def admin_get_bookings(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(status_code=403, detail="Not admin")

    db = SessionLocal()
    bookings = db.query(Appointment).order_by(Appointment.datetime).all()
    db.close()
    return bookings


# ✔ ПІДТВЕРДИТИ ЗАПИС
@app.put("/booking/{booking_id}/confirm")
def confirm_booking(booking_id: int, request: Request):
    if not request.session.get("admin"):
        raise HTTPException(status_code=403)

    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == booking_id).first()

    if not booking:
        db.close()
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.status = "confirmed"
    db.commit()

    # 📲 TELEGRAM MESSAGE
    send_telegram(
        f"💈 Запис підтверджено!\n\n"
        f"👤 {booking.client_name}\n"
        f"📞 {booking.phone}\n"
        f"✂️ {booking.service}\n"
        f"🕐 {booking.datetime}"
    )

    db.close()
    return {"status": "confirmed"}


# ✖ СКАСУВАТИ ЗАПИС
@app.put("/booking/{booking_id}/cancel")
def cancel_booking(booking_id: int, request: Request):
    if not request.session.get("admin"):
        raise HTTPException(status_code=403)

    db = SessionLocal()
    booking = db.query(Appointment).filter(Appointment.id == booking_id).first()

    if not booking:
        db.close()
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.status = "cancelled"
    db.commit()

    # 📲 TELEGRAM MESSAGE
    send_telegram(
        f"❌ Запис скасовано\n\n"
        f"👤 {booking.client_name}\n"
        f"📞 {booking.phone}\n"
        f"✂️ {booking.service}\n"
        f"🕐 {booking.datetime}"
    )

    db.close()
    return {"status": "cancelled"}

@app.on_event("startup")
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_reminders, "interval", minutes=1)
    scheduler.start()

    # =====================================================
# 📅 AVAILABLE TIME SLOTS
# =====================================================

# =====================================================
# 📅 AVAILABLE TIME SLOTS (FINAL VERSION)
# =====================================================
@app.get("/available-times")
def available_times(date: str):
    db = SessionLocal()

    WORK_START = 10
    WORK_END = 19

    selected_date = datetime.strptime(date, "%Y-%m-%d")

    start_day = selected_date.replace(hour=0, minute=0, second=0)
    end_day = selected_date.replace(hour=23, minute=59, second=59)

    # беремо ВСІ записи на день (крім скасованих)
    bookings = db.query(Appointment).filter(
        Appointment.datetime >= start_day,
        Appointment.datetime <= end_day,
        Appointment.status != "cancelled"
    ).all()

    busy_hours = [b.datetime.strftime("%H:00") for b in bookings]

    free_slots = []
    for hour in range(WORK_START, WORK_END):
        slot = f"{hour:02d}:00"
        if slot not in busy_hours:
            free_slots.append(slot)

    db.close()
    return free_slots