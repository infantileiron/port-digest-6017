import json
from fastapi import HTTPException,Response
from src.models.entities import Disclosure
from src.services.repository import get_receipt
from src.services.business import dump
from src.services.disclosure import public_view
def export_receipt(s,i):
 r=get_receipt(s,i)
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="port-digest-{r.report_day}-{i}.json"'})
def export_disclosure(s,i):
 d=s.get(Disclosure,i)
 if not d:raise HTTPException(404,'公开记录不存在')
 return Response(json.dumps(public_view(d),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="port-public-{d.report_day}-{d.id}.json"'})
