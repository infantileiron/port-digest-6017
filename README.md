# 临港 · 港站晨报定时分发

把昨日计划到发、延误分位数与交接班晨报串起来，由真实worker到点生成站内收件箱回执，保留冻结来源。

## 场景与工作流

临港联运运营北站、南站和东港三个港站，每天约150条班次记录。现行工作流是值班员导出 `临港到发_20261114.xlsx`，分析员按日期筛选后手算延误，负责人再把表格转发给下一班。痛点是跨午夜班次归错日、未到发被当准点、重复转发后分不清同一口径。上游为港站计划/实际到发记录；本项目替代日界归档、晨报试算和定时分发；下游为站内值班室交接班。

三个核心实体：Arrival到发记录、Subscription晨报订阅、Receipt分发回执，另有用户、审计和公开披露三表。五页：到发台账、晨报预览、订阅计划、分发回执、公开披露。回执支持值班复核与下载，原始记录修订不改变已分发晨报；公开披露页供内部申请并向合作站展示聚合结果。

|角色|权限|典型动作|
|---|---|---|
|admin|全部；独占订阅配置/值班复核/审计/公开重试|设定08:30晨报并核对回执；立即核算待处理公开申请|
|analyst|到发录入/修订、晨报试算、读取计划回执、提交公开申请、导出|补录跨午夜班次；发起合作站公开申请|
|viewer|业务只读与回执/公开导出|下载冻结晨报与公开 JSON；后端拒绝写入或申请|

## 快速启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 [localhost:18212](http://localhost:18212)，API [localhost:19212/docs](http://localhost:19212/docs)，PostgreSQL映射17712。账号 `admin@demo.local`、`analyst@demo.local`、`viewer@demo.local`，密码均 `Demo123!`。种子为3账号、150条昨日计划到发、3条暂停订阅；不会自动对外发送。自然编号幂等，重复运行不覆盖人工修订；种子日期为首次启动的昨日，后续日需业务录入新记录。

## 一日业务剧本

1. 08:00 viewer 查看LG-001至LG-150，核对未到发为空。
2. 08:05 analyst 录入 `LG-151`，北站，计划2026-11-14 23:55，实际2026-11-15 00:05，交接说明为跨午夜。
3. 08:10 在晨报预览选择2026-11-14和北站，检查该班次仍归14日、延误10分钟。
4. 08:15 admin 创建“北站08:30值班晨报”，站内收件箱“北站值班室”，每日08:30，启用。
5. 演示时可把“首次到点”设为未来10秒；不需要任何手动发送按钮。
6. 08:30 worker每秒检查到点订阅，冻结昨日来源并写入回执。
7. 08:31 刷新分发回执，核对P50/P95、完成/未到发人数和来源checksum。
8. 08:35 admin 写入“跨日班次已核对”复核意见；viewer下载 `port-digest-<业务日>-<回执id>.json`。
9. 09:00 analyst 在公开披露页提交“2026-11-14 / 北站+南站”申请；worker 每秒核算，通过后变为已公开并在“已公开”区出现聚合记录。
10. 09:05 试算申请“2026-11-14 / 北站”时，若会把南站切出不足5个班次，则显示已拒绝并列出冲突人群；安全组合照常发布。
11. 09:10 viewer 只看到到发数、延误数、延误总分钟，下载 `port-public-<业务日>-<公开id>.json`，其中无班次号、时间或备注。

## 计算与调度口径

**归档**按计划到发时间转Asia/Shanghai后的自然日，而非实际到达日。后端时间输入必须有偏移（如+08:00），统一保存UTC；前端datetime-local明确按上海解释。实际可空，表示未到发。时间差超过3天拒绝，提示核对。

**延误**=max(0,实际−计划)分钟，提前到达记0。已到发才进入延误率与分位数分母；未到发单独计数。P50/P95使用排序后位置(n−1)p的线性插值；没有已到发样本时分位数、均值和延误率为null，页面显示“未定义”。输出带完整选中来源、口径版本与SHA256 checksum。

**到点调度**由worker每秒扫描UTC next_run_at，Redis锁串行化扫描，数据库用行锁和唯一约束 `(subscription_id, report_day)` 防止同订阅同报告日重复入箱。首次时间可设未来数秒进行真实调度验证；以后按Asia/Shanghai每日HH:MM安排。到点或服务中断恢复时只生成“执行时刻的最新昨日”一份，不补历史天；同日再次到点只推进next_run_at，不新增回执。暂停订阅不执行。修订订阅如果未填写首次时间，会重新安排下一个每日时刻；恢复暂停也按此规则。

晨报“送达”表示已提交站内数据库收件箱，不是SMTP邮件。回执保存冻结payload，DB提交后附加写共享产物卷；附加文件失败不影响DB回执和导出。值班复核仅管理员可做，一次复核不可覆盖，且不改变payload。支持单worker；唯一约束与锁防重复，但不声称对外消息的exactly-once。

## 对外公开口径

对外公开按**上海计划日 × 港站组合**聚合成一行明细：到发数、延误数（延误>0的已到发班次）、延误总分钟（未到发不计入延误分钟）。公开查询与下载只含这三个聚合值和口径版本、checksum，**不返回班次号、计划/实际时间或备注**；内部晨报、回执与台账照旧。

- **冻结来源**：同一计划日只在首次成功公开时把当日全部港站快照写入 `disclosure_sources`；之后同日申请（含补申请）一律沿用该快照，不受后续修订或新增记录影响。若该计划日完全没有任何到发记录，则拒绝并**不冻结空来源**（避免把尚未录入的日子永久钉成 0），待班次录入后可重新申请。快照冻结后，某港站在冻结来源中没有记录属于“空人群”，可正常公开 0（以冻结来源为准，即使之后又补录了该站班次；需要纳入只能等下一计划日）。
- **累计小样本约束（k=5）**：把当日“已公开组合 ∪ 本次组合”覆盖的港站按成员签名切成互不相交人群（Venn 原子）。同一批公开统计相减可还原出每个人群，因此**每个非空人群必须至少 5 个班次**；空人群不参与也无需满足。举例：先公开北+南、再公开南+东，会把北单独切出，若北不足5则拒绝；先公开北站、再公开北+南，若南不足5则拒绝。被拒绝的申请仍落一条已拒绝记录，附冲突人群、人口数和判定说明。只有累计范围覆盖到的港站参与切分；未被任何组合覆盖的港站无法由已公开统计反推。
- **状态与原子性**：申请从 `pending` 到 `published` 或 `rejected`。判定、公开记录、来源冻结与审计在同一事务提交；发布前中断整体回滚，申请保持 pending，worker 下轮或管理员重试。相同计划日与组合已有公开时，重复申请沿用既有公开记录（`duplicate_of`），不重复发布。
- **并发**：同一计划日的判定用 PostgreSQL 事务级 advisory lock 串行化，并对待判定申请行加锁；并发申请不会各自基于旧状态，累计约束始终成立。worker 每秒处理 pending 申请，单条失败只记录日志并保留 pending。

接口：内部 `GET/POST /disclosure-applications`、`GET /disclosure-applications/{id}`、`POST /disclosure-applications/{id}/retry`（仅 admin、仅 pending）；对外 `GET /public/disclosures`、`/{id}`、`/{id}/export`。公开接口只需登录（与回执一致），不向未认证方暴露任何数据。

## 工程、环境变量和开发

Python3.11/FastAPI/SQLAlchemy/PyJWT、原生ES modules/CSS、Nginx、PostgreSQL16、Redis7。恰好frontend/backend/worker/db/redis五服务，各有健康检查；backend等db/redis、worker还等backend、frontend等backend。Redis实际提供调度锁；worker心跳 `/tmp/heartbeat`，DB/Redis/产物分别命名卷。Nginx `/api/` 去前缀代理后端根路由。公开申请核算不依赖 Redis，直接由 worker 在调度轮之外执行。

`.env.example`列出COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO、NETWORK_SUBNET。显式子网10.253.113.0/24规避当前机默认地址池耗尽，可按环境调整。演示凭据应在正式部署替换。清理本项目用 `docker compose down -v --remove-orphans`。

本地开发：启动db/redis，backend安装requirements，设置DATABASE_URL/REDIS_URL/JWT_SECRET，再运行 `uvicorn src.main:app --reload` 和 `python -m src.worker`；前端仍建议用Nginx同源代理。后端目录src按routes/controllers/services/models/schemas/middlewares/config/utils/constants分工；前端src按api/stores/pages/components/hooks/utils/constants/types/router分工。ORM首次建表，migrations保留实际初始DDL，无在线迁移执行器。

枚举：后端 `src/constants/enums.py`、`src/schemas/business.py` 与前端 `src/constants/enums.js` 定义ROLES、STATIONS、RECEIPT_STATES、DISCLOSURE_STATES与DISCLOSURE_MIN_GROUP；TIMEZONE固定Asia/Shanghai。共用表格、表单、状态标签、晨报摘要组件；表单hooks、HTML转义和日期工具；请求ID/安全响应头两个中间件，业务审计与全局错误恢复。测试与截图在 `../../test-artifacts/gb-3113/`，不放源码内。

范围：逐条录入/完整修订，无CSV导入、删除或分页；只有三个固定港站与上海时区。公开申请只支持固定三站的非空组合，不支持任意站点自定义；公开接口不提供匿名访问，合作站使用站内账号或由内部导出后转发。站内收件箱按名称记录，当前所有登录角色可读业务回执与公开聚合，无多租户邮箱隔离；不连接邮件、短信或外部IM。Google Fonts离线时字体回退。许可证MIT，见LICENSE。
