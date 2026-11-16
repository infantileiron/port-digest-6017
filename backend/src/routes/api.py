from fastapi import APIRouter,Depends,HTTPException
from src.config.database import db
from src.models.entities import User,Subscription,Receipt,Audit,DisclosureApplication,Disclosure
from src.schemas.business import Login,ArrivalInput,SubscriptionInput,PreviewInput,ReviewInput,DisclosureInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.utils.time import now_utc,yesterday,SH
from src.services.business import audit,dump
from src.services.repository import arrival_rows,save_arrival,save_subscription,get_receipt
from src.services.digest import calculate
from src.services import disclosure as disclosure_service
from src.controllers.business import export_receipt,export_disclosure
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/context')
def context(u=Depends(current)):
 now=now_utc();return {'now':now.isoformat(),'yesterday':yesterday(now),'timezone':'Asia/Shanghai'}
@router.get('/arrivals')
def arrivals(u=Depends(current),s=Depends(db)):return arrival_rows(s)
@router.post('/arrivals')
def create_arrival(data:ArrivalInput,u=Depends(editor),s=Depends(db)):
 r=save_arrival(s,data);audit(s,u,'录入班次 '+r.code);return dump(r)
@router.put('/arrivals/{i}')
def edit_arrival(i:int,data:ArrivalInput,u=Depends(editor),s=Depends(db)):
 r=save_arrival(s,data,i);audit(s,u,'修订班次 '+r.code);return dump(r)
@router.post('/preview')
def preview(data:PreviewInput,u=Depends(editor),s=Depends(db)):
 result=calculate(arrival_rows(s),data.report_day.isoformat(),data.station);audit(s,u,'晨报试算 '+data.report_day.isoformat());return result
@router.get('/subscriptions')
def subscriptions(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Subscription).order_by(Subscription.id).all()]
@router.post('/subscriptions')
def create_subscription(data:SubscriptionInput,u=Depends(admin),s=Depends(db)):
 r=save_subscription(s,data);audit(s,u,'创建订阅 '+r.name);return dump(r)
@router.put('/subscriptions/{i}')
def edit_subscription(i:int,data:SubscriptionInput,u=Depends(admin),s=Depends(db)):
 r=save_subscription(s,data,i);audit(s,u,'修订订阅 '+r.name);return dump(r)
@router.get('/receipts')
def receipts(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Receipt).order_by(Receipt.id.desc()).all()]
@router.get('/receipts/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):return export_receipt(s,i)
@router.post('/receipts/{i}/review')
def review(i:int,data:ReviewInput,u=Depends(admin),s=Depends(db)):
 r=get_receipt(s,i)
 if r.state=='reviewed':raise HTTPException(409,'回执已复核，不覆盖原复核意见')
 r.state='reviewed';r.review_note=data.note;s.commit();audit(s,u,'复核晨报回执 '+str(i));return dump(r)

# 内部公开申请：待核算 -> 已公开/已拒绝；判定与公开记录同事务生效。
def _application_view(s,app):
 v=dump(app);v['stations']=list(app.stations);v['note']=app.request_note;v['basis']=app.basis
 v['conflict_count']=len((app.basis or {}).get('conflicts',[]))
 v['disclosure']=disclosure_service.public_view(s.get(Disclosure,app.disclosure_id)) if app.disclosure_id else None
 return v
@router.get('/disclosure-applications')
def disclosure_applications(u=Depends(current),s=Depends(db)):
 return [_application_view(s,a) for a in s.query(DisclosureApplication).order_by(DisclosureApplication.id.desc()).all()]
@router.post('/disclosure-applications')
def create_disclosure_application(data:DisclosureInput,u=Depends(editor),s=Depends(db)):
 try:stations,key=disclosure_service.canonical_stations(data.stations)
 except ValueError as exc:raise HTTPException(422,str(exc))
 app=DisclosureApplication(report_day=data.report_day.isoformat(),station=key,stations=stations,requested_by=u.email,request_note=data.note,created_at=now_utc().isoformat(),state='pending')
 s.add(app);s.flush()
 s.add(Audit(actor=u.email,action='提交公开申请 #%s / %s %s'%(app.id,app.report_day,key),created=now_utc().isoformat()))
 s.commit();return _application_view(s,app)
@router.get('/disclosure-applications/{i}')
def disclosure_application(i:int,u=Depends(current),s=Depends(db)):
 app=s.get(DisclosureApplication,i)
 if not app:raise HTTPException(404,'公开申请不存在')
 return _application_view(s,app)
@router.post('/disclosure-applications/{i}/retry')
def retry_disclosure_application(i:int,u=Depends(admin),s=Depends(db)):
 app=s.get(DisclosureApplication,i)
 if not app:raise HTTPException(404,'公开申请不存在')
 if app.state!='pending':raise HTTPException(409,'申请已判定（%s），不重新核算'%app.state)
 try:app=disclosure_service.decide(s,i,u.email)
 except Exception:
  s.rollback();raise HTTPException(503,'核算中断，申请保持待核算，可重试')
 return _application_view(s,app)

# 对外公开查询：只含聚合值、口径与校验；不含班次、任何时间或备注。
@router.get('/public/disclosures')
def public_disclosures(u=Depends(current),s=Depends(db)):
 return [disclosure_service.public_view(d) for d in s.query(Disclosure).order_by(Disclosure.id.desc()).all()]
@router.get('/public/disclosures/{i}')
def public_disclosure(i:int,u=Depends(current),s=Depends(db)):
 d=s.get(Disclosure,i)
 if not d:raise HTTPException(404,'公开记录不存在')
 return disclosure_service.public_view(d)
@router.get('/public/disclosures/{i}/export')
def public_disclosure_export(i:int,u=Depends(current),s=Depends(db)):return export_disclosure(s,i)
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
