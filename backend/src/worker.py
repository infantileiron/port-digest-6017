import os,time,logging
from pathlib import Path
import redis
from redis.exceptions import LockError
from src.config.database import Session
from src.services.scheduler import run_due
from src.services.disclosure import process_pending
from src.utils.time import now_utc
r=redis.Redis.from_url(os.environ['REDIS_URL'])

def tick(now=None):
 """一轮：调度锁内执行到点订阅；公开申请独立核算，单条失败下轮重试。"""
 Path('/tmp/heartbeat').touch()
 try:
  with r.lock('port-digest:scheduler',timeout=20,blocking_timeout=0):
   with Session() as s:run_due(s,now or now_utc())
 except LockError:pass
 except Exception:logging.exception('scheduler tick failed')
 # 公开申请不依赖调度锁：判定自身用数据库日锁与单事务保证串行和原子。
 try:return process_pending()
 except Exception:logging.exception('disclosure tick failed');return []

if __name__=='__main__':
 while True:
  tick()
  time.sleep(1)
