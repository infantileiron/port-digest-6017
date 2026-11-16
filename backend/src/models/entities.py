from sqlalchemy import Column,Integer,String,JSON,Text,Boolean,ForeignKey,UniqueConstraint
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True,nullable=False);password=Column(String(200));role=Column(String(20))
class Arrival(Base):
 __tablename__='arrivals'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);station=Column(String(30));planned_at=Column(String(40));actual_at=Column(String(40),nullable=True);note=Column(Text,default='')
class Subscription(Base):
 __tablename__='subscriptions'
 id=Column(Integer,primary_key=True);name=Column(String(100),unique=True,nullable=False);station=Column(String(30));daily_at=Column(String(5));recipient=Column(String(80));enabled=Column(Boolean,default=False);next_run_at=Column(String(40));last_run_at=Column(String(40),nullable=True)
class Receipt(Base):
 __tablename__='receipts'
 __table_args__=(UniqueConstraint('subscription_id','report_day',name='uq_receipt_subscription_day'),)
 id=Column(Integer,primary_key=True);subscription_id=Column(Integer,ForeignKey('subscriptions.id'));report_day=Column(String(10));recipient=Column(String(80));created_at=Column(String(40));state=Column(String(20),default='delivered');payload=Column(JSON);review_note=Column(Text,default='')
# 公开披露：同一上海计划日只在首次成功公开时冻结一份来源，之后同日申请沿用。
class DisclosureSource(Base):
 __tablename__='disclosure_sources'
 __table_args__=(UniqueConstraint('report_day',name='uq_disclosure_source_day'),)
 id=Column(Integer,primary_key=True);report_day=Column(String(10),nullable=False);snapshot=Column(JSON,nullable=False);fingerprint=Column(String(64),nullable=False);created_at=Column(String(40));created_by=Column(String(100))
class DisclosureApplication(Base):
 __tablename__='disclosure_applications'
 id=Column(Integer,primary_key=True);report_day=Column(String(10),nullable=False);station=Column(String(80),nullable=False);stations=Column(JSON,nullable=False);requested_by=Column(String(100));request_note=Column(Text,default='');created_at=Column(String(40));state=Column(String(20),default='pending');decided_at=Column(String(40),nullable=True);decided_by=Column(String(100),nullable=True);decision_note=Column(Text,default='');basis=Column(JSON,nullable=True);disclosure_id=Column(Integer,nullable=True)
class Disclosure(Base):
 __tablename__='disclosures'
 __table_args__=(UniqueConstraint('report_day','station',name='uq_disclosure_day_station'),)
 id=Column(Integer,primary_key=True);application_id=Column(Integer,ForeignKey('disclosure_applications.id'));report_day=Column(String(10),nullable=False);station=Column(String(80),nullable=False);stations=Column(JSON,nullable=False);source_id=Column(Integer,ForeignKey('disclosure_sources.id'),nullable=False);published_at=Column(String(40));published_by=Column(String(100));payload=Column(JSON);checksum=Column(String(64));version=Column(String(60));rule=Column(Text)
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
