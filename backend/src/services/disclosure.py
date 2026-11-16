"""公开申请核算：按上海计划日与港站组合冻结来源、切分累计范围、原子判定并发布。

安全口径（k=5）
1. 同一计划日只使用首次成功公开时冻结的来源；之后同日申请沿用同一份快照，
   不受后续修订影响。
2. 把“已公开组合 ∪ 本次组合”覆盖到的港站，按各组合的成员签名切成互不相交的
   人群（Venn 原子）。同一批统计相减可以还原出每个人群，因此每个非空人群必须
   至少含 5 个班次。未被任何组合覆盖的港站不在累计公开范围内，无法由已公开
   统计反推，不参与切分。
3. 判定（application.state）与公开记录（disclosures）在同一事务提交；发布前
   中断整体回滚，申请保持 pending，可安全重试且不会重复发布。
4. 同一计划日的判定由事务级 advisory lock 串行化，并发申请不会各自基于旧状态。
"""
import hashlib
import json

from sqlalchemy import text

from src.config.database import Session
from src.models.entities import (
    Arrival,
    Audit,
    Disclosure,
    DisclosureApplication,
    DisclosureSource,
)
from src.utils.time import SH, aware, now_utc

ALL_STATIONS = ('北站', '南站', '东港')
MIN_GROUP_SIZE = 5
VERSION = 'planned-day-station-k5-v1'
PUBLIC_RULE = (
    '按上海计划日与港站组合聚合；公开到发数、延误数和延误总分钟，'
    '不公开班次、时间及备注。同一计划日沿用首次公开冻结来源；'
    '累计公开范围切出的每个非空人群至少含 5 个班次。'
)

def canonical_stations(stations):
    if not stations:
        raise ValueError('至少选择一个港站')
    if len(stations) != len(set(stations)):
        raise ValueError('港站组合不能重复')
    chosen = set(stations)
    ordered = [s for s in ALL_STATIONS if s in chosen]
    if len(ordered) != len(chosen):
        raise ValueError('港站组合包含未知项')
    return ordered, '+'.join(ordered)


def _lock_day(s, day):
    """按上海计划日串行化判定；事务结束（提交或回滚）自动释放。"""
    if s.get_bind().dialect.name == 'postgresql':
        key = int.from_bytes(
            hashlib.sha256(('disclosure:' + day).encode()).digest()[:8], 'big', signed=True
        )
        s.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})


def _snapshot_for_day(s, day):
    """当日全部港站的最小快照：保留聚合所需字段与稳定性指纹，不含备注。"""
    rows = []
    for r in s.query(Arrival).order_by(Arrival.planned_at, Arrival.id).all():
        try:
            if aware(r.planned_at).astimezone(SH).date().isoformat() != day:
                continue
        except ValueError:
            continue
        rows.append(
            {
                'id': r.id,
                'station': r.station,
                'planned_at': r.planned_at,
                'actual_at': r.actual_at,
            }
        )
    return rows


def _fingerprint(snapshot):
    raw = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def _delay_minutes(row):
    if not row.get('actual_at'):
        return None
    return max(0.0, (aware(row['actual_at']) - aware(row['planned_at'])).total_seconds() / 60)


def aggregate(snapshot, stations):
    station_set = set(stations)
    rows = [r for r in snapshot if r['station'] in station_set]
    delays = [d for d in (_delay_minutes(r) for r in rows) if d is not None]
    return {
        'stations': list(stations),
        'arrivals': len(rows),
        'delayed': sum(1 for d in delays if d > 0),
        'delay_minutes': round(sum(delays), 2),
    }


def partition_atoms(scopes):
    """把累计公开范围覆盖的港站按成员签名切成互不相交的人群。"""
    unique = []
    seen = set()
    for scope in scopes:
        key = frozenset(scope)
        if key and key not in seen:
            seen.add(key)
            unique.append(key)
    universe = set().union(*unique) if unique else set()
    groups = {}
    for station in ALL_STATIONS:
        if station not in universe:
            continue
        signature = tuple(station in scope for scope in unique)
        groups.setdefault(signature, []).append(station)
    return [
        {
            'stations': members,
            'covered_by': [scope for scope, flag in zip(unique, signature) if flag],
        }
        for signature, members in groups.items()
    ]


def evaluate(snapshot, published_scopes, candidate):
    """返回安全判定与逐个人群的依据；可重复调用，无副作用。"""
    candidate = frozenset(candidate)
    scopes = list(published_scopes)
    if candidate not in scopes:
        scopes.append(candidate)
    atoms = []
    conflicts = []
    for atom in partition_atoms(scopes):
        population = aggregate(snapshot, atom['stations'])['arrivals']
        record = {
            'stations': atom['stations'],
            'population': population,
            'minimum': MIN_GROUP_SIZE,
            'nonempty': population > 0,
            'ok': population == 0 or population >= MIN_GROUP_SIZE,
            'covered_by': [list(x) for x in atom['covered_by']],
        }
        atoms.append(record)
        if record['nonempty'] and not record['ok']:
            conflicts.append(record)
    return {
        'safe': not conflicts,
        'minimum': MIN_GROUP_SIZE,
        'published_scopes': [list(x) for x in published_scopes],
        'candidate': aggregate(snapshot, candidate),
        'atoms': atoms,
        'conflicts': conflicts,
    }


def _conflict_note(conflicts):
    parts = [
        '%s 仅 %s 个班次（至少 %s）'
        % ('+'.join(c['stations']), c['population'], c['minimum'])
        for c in conflicts
    ]
    return '拒绝：累计公开范围切出小样本人群 — ' + '；'.join(parts)


def _with_source(basis, source, snapshot):
    basis['source'] = {
        'frozen': source is not None,
        'fingerprint': source.fingerprint if source is not None else _fingerprint(snapshot),
    }
    return basis


def _published(s, day):
    return s.query(Disclosure).filter_by(report_day=day).order_by(Disclosure.id).all()


def decide(s, application_id, actor='system'):
    """单事务判定一条待核算申请；返回最新申请对象。失败由调用方回滚。"""
    app = s.get(DisclosureApplication, application_id)
    if app is None:
        return None
    day = app.report_day
    _lock_day(s, day)
    app = (
        s.query(DisclosureApplication)
        .filter_by(id=application_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if app is None or app.state != 'pending':
        return app

    source = s.query(DisclosureSource).filter_by(report_day=day).first()
    snapshot = source.snapshot if source is not None else _snapshot_for_day(s, day)
    stations = list(app.stations)
    candidate = frozenset(stations)
    now = now_utc().isoformat()

    existing = s.query(Disclosure).filter_by(report_day=day, station=app.station).first()
    if existing is not None:
        # 相同计划日+组合已公开：沿用既有披露，不再生成第二条记录（幂等）。
        basis = _with_source(
            {
                'safe': True,
                'minimum': MIN_GROUP_SIZE,
                'published_scopes': [list(d.stations) for d in _published(s, day)],
                'candidate': aggregate(snapshot, stations),
                'atoms': [],
                'conflicts': [],
                'duplicate_of': existing.id,
            },
            source,
            snapshot,
        )
        app.state = 'published'
        app.decided_at = now
        app.decided_by = actor
        app.decision_note = (
            '已公开：相同计划日与港站组合已有披露 #%s，本次沿用冻结结果，不重复发布。'
            % existing.id
        )
        app.basis = basis
        app.disclosure_id = existing.id
        s.add(Audit(actor=actor, action='公开申请沿用 #%s / 披露 #%s' % (app.id, existing.id), created=now))
        s.flush()
        _commit(s)
        return app

    published_scopes = [frozenset(d.stations) for d in _published(s, day)]
    basis = _with_source(evaluate(snapshot, published_scopes, candidate), source, snapshot)

    # 整日无任何记录时不冻结空来源，避免把尚未录入的计划日永久钉成 0；可待数据到达后重申。
    if source is None and not snapshot:
        app.state = 'rejected'
        app.decided_at = now
        app.decided_by = actor
        app.decision_note = '拒绝：该计划日尚无到发记录，不冻结空来源；请待班次录入后重新申请。'
        app.basis = basis
        s.add(Audit(actor=actor, action='公开申请拒绝 #%s / 计划日无记录' % app.id, created=now))
        s.flush()
        _commit(s)
        return app

    if not basis['safe']:
        app.state = 'rejected'
        app.decided_at = now
        app.decided_by = actor
        app.decision_note = _conflict_note(basis['conflicts'])
        app.basis = basis
        s.add(Audit(actor=actor, action='公开申请拒绝 #%s' % app.id, created=now))
        s.flush()
        _commit(s)
        return app

    if source is None:
        source = DisclosureSource(
            report_day=day,
            snapshot=snapshot,
            fingerprint=_fingerprint(snapshot),
            created_at=now,
            created_by=actor,
        )
        s.add(source)
        s.flush()
        basis['source'] = {'frozen': True, 'fingerprint': source.fingerprint}

    public_payload = {
        'report_day': day,
        'stations': stations,
        'arrivals': basis['candidate']['arrivals'],
        'delayed': basis['candidate']['delayed'],
        'delay_minutes': basis['candidate']['delay_minutes'],
    }
    checksum = hashlib.sha256(
        json.dumps(public_payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    disclosure = Disclosure(
        application_id=app.id,
        report_day=day,
        station=app.station,
        stations=stations,
        source_id=source.id,
        published_at=now,
        published_by=actor,
        payload=public_payload,
        checksum=checksum,
        version=VERSION,
        rule=PUBLIC_RULE,
    )
    s.add(disclosure)
    s.flush()
    app.state = 'published'
    app.decided_at = now
    app.decided_by = actor
    app.decision_note = (
        '核算通过：累计公开范围切出的每个非空人群均不少于 %s 个班次。' % MIN_GROUP_SIZE
    )
    app.basis = basis
    app.disclosure_id = disclosure.id
    s.add(
        Audit(
            actor=actor,
            action='公开申请通过 #%s / 披露 #%s' % (app.id, disclosure.id),
            created=now,
        )
    )
    s.flush()
    _commit(s)
    return app


def _commit(s):
    s.commit()


def decide_safely(application_id, actor='system'):
    """独立会话判定；任何异常都回滚，申请保持 pending 供重试。"""
    with Session() as s:
        try:
            return decide(s, application_id, actor)
        except Exception:
            s.rollback()
            raise


def process_pending():
    """worker 每轮调用：逐条核算 pending 申请；单条失败不影响其他申请。"""
    import logging

    with Session() as s:
        ids = [
            row[0]
            for row in s.query(DisclosureApplication.id)
            .filter_by(state='pending')
            .order_by(DisclosureApplication.id)
            .all()
        ]
    done = []
    for i in ids:
        try:
            app = decide_safely(i)
            if app is not None:
                done.append((i, app.state))
        except Exception:
            logging.exception('disclosure decision failed for application %s; will retry', i)
    return done


def public_view(d):
    """对外视图：只含聚合值、口径版本与校验；不含班次、任何时间与备注。"""
    return {
        'id': d.id,
        'report_day': d.report_day,
        'stations': list(d.stations),
        'arrivals': d.payload['arrivals'],
        'delayed': d.payload['delayed'],
        'delay_minutes': d.payload['delay_minutes'],
        'version': d.version,
        'checksum': d.checksum,
        'rule': d.rule,
    }
