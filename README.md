# 诊所耗材补货计划

面向诊所库管的本地工作台。内置业务样例覆盖基层诊所耗材需求预测、断供回补与批量补货。样例采用确定性构造，适合复现实验和核查边界行为。

## 启动

```sh
docker compose up --build -d
```

打开 `http://127.0.0.1:18203/` 查看耗材补货单。左侧六个入口可展开运行证据。调整「补货箱额（箱）」，点击「重算补货」比较处置结果。结束后执行 `docker compose down --remove-orphans`。

## 独立业务模块

- 领用流水 `usage_receipts`
- 可售修复 `outage_today`
- 用量建模 `demand_smoothing`
- 残差区间 `reorder_bands`
- 整箱分配 `carton_budget`
- 消耗复盘 `consumption_review`

## 查看运行结果

- `GET /api/overview` 返回默认运行及其指纹。
- `POST /api/scenario` 接收 `{"capacity": 3}`。入口接受 1–100 的整数，应用样例时使用该业务额度。
- `GET /api/stages/consumption_review` 查看该环节的独立证据，支持 `?capacity=3`。

```sh
docker compose exec -T app python -m clinicstock.delivery evaluate --capacity 3
docker compose exec -T app pytest -q
```

数据和模型约定见 [业务契约](docs/SPEC.md)。模块、例外规则与验证入口见 [业务深度](docs/DEPTH.md)。
