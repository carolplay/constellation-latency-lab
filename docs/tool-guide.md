# 两项工具的接口与模型范围

## 1. 动态星座覆盖图

网页入口：`coverage.html`。Python入口：`constellation-cover`。

输入高度h、倾角i、轨道面数P、每面星数S、Walker相位F、RAAN原点、初始相位、最低仰角、UTC历元和时间范围。支持多个圆轨道层。Delta面在360°均布；Star采用180°/P间距、排布0到180°−180°/P；部分面模式的跨度包含两端。F满足0≤F<P，邻面平近点角偏移360F/(PS)。

轨道为解析Kepler＋长期J2，使用GMST做一次ECEF旋转；没有拖曳、短周期J2、极移、岁差章动或机动。地面接入按WGS84椭球法向计算。足印求仰角边界，锥体是球面近似；均不是实际天线波束。未计入机械指向、光学误差、天气、地形和容量。航线97点的绿点不代表端到端网络连通。

“新建星座”在本机保存配置；导出JSON可给时延工具使用，导出CZML可在Cesium中播放。新方案不自动提交到公共预设库。有限采样100%不能作为连续时间或永久运行证明。

## 2. 网络时延模拟

网页入口：`latency.html`。Python入口：`constellation-latency`。

| 模式 | 包含 | 未包含 |
|---|---|---|
| 网页/Python geometry | 仰角、80km大气边界（可配）、链路距离、拓扑、Dijkstra、传播和处理开销 | PAT、有限星地天线、捕获、切星、队列、天气、光链路预算、容量 |
| Python engineering | 上述及现有FOV、LVLH标称方向、slew、Doppler、星间捕获、地面一/双天线状态机 | 厂商标定误差、真实链路预算、天气、队列、容量、因果包级传播 |

grid：各轨道层的同面前后与相邻面同编号边，每星最多四邻居。Star/部分面的首尾接缝不闭合，跨轨道层不连边。complete：所有几何允许的边，跨层可连；是假设无限终端的乐观图，最多150星。没有从实际轨道位置推测运营商真实接触计划。

星间边权=d/c+τproc；星地边权=d/c+τproc/2+τmodem。这样每个经过的卫星只计费一次。RTT=2×同一快照对称OWTT。中断的时延为缺失值。输出：平均RTT、在线P1/P99、在线P99−P1跨度、接通率、最长中断、路径变化；工程模式另输出真实模型中的接入事件。

P99−P1不等于包间抖动。geometry中的路径变化不等于实际切星次数。全天断网超过1%时无条件P99为无穷。58.9/155/7.97ms为情景参考，不是本项目实测SLA。

## 共用配置（schema_version=1）

```json
{
  "schema_version": 1,
  "name": "Walker candidate",
  "shells": [{"pattern":"delta","planes":6,"sats_per_plane":12,
    "altitude_km":1180,"inclination_deg":50,"walker_f":5,
    "raan_start_deg":0,"phase_deg":0,"j2":true}],
  "simulation": {"route":"LD4-TOKYO","duration_s":86400,
    "step_s":60,"epoch":"2026-10-12T00:00:00Z"},
  "topology": "grid",
  "physics": {"min_elevation_deg":20,"atmosphere_km":80,
    "max_isl_range_km":6000,"satellite_processing_us":5,
    "ground_modem_ms":0.5}
}
```

工程模式的额外physics键见`hftsim/config.py`中的Physics。网页导入后保留这些额外键，但几何计算不使用它们。浏览器支持≤500星、≤20000快照、≤7天；圆轨道以60s样本生成CZML，5阶Lagrange插值（短区间自动降阶），不是直接在浏览器每帧数值积分。

## 新增公共预设

1. 添加`configs/<id>.json`。
2. 在`data/catalog.json`添加名称与配置地址，可立即供时延工具选择。
3. 若要添加覆盖图公共预设，先获得独立统计，再在`data/preset-metrics.json`记录真实结果与采样口径；没有统计的新方案用“新建星座”，不要填写假定100%。
4. 运行`python scripts/build_site.py`，再预览与发布。

构建只导出已配置的星历与既有统计，不重跑研究扫描。机械、光学误差校准与连续时间验收不在当前发布范围。
