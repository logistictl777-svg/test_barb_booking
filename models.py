from sqlalchemy import Column,Integer,String,DateTime
from database import Base

class Appointment(Base):
    __tablename__="appointments"

    id=Column(Integer,primary_key=True,index=True)
    client_name=Column(String)
    phone=Column(String)
    service=Column(String)
    datetime=Column(DateTime)
    status=Column(String)