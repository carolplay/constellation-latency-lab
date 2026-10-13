# Constellation Latency Lab

两个可复用工具：**动态星座几何覆盖图**与**网络时延模拟**。共用版本化 JSON 配置，支持自定义 Walker Delta / Star、多个轨道层、导入导出和可复现的快照统计。

**[打开公开工具站点](https://walker-delta-coverage-guoya.polyguoyang.chatgpt.site/)** · [覆盖图](https://walker-delta-coverage-guoya.polyguoyang.chatgpt.site/coverage.html) · [网络时延](https://walker-delta-coverage-guoya.polyguoyang.chatgpt.site/latency.html) · [模型与接口说明](docs/tool-guide.md)

## 1. 动态星座覆盖图

选择既有预设，或点击“新建星座”输入高度、倾角、轨道面数、每面星数、面间相位、仰角及 UTC 历元。可添加多个轨道层；新方案保存在你的本机浏览器，可下载配置 JSON 或 CZML。

- 圆轨道 Kepler＋长期 J2；ECEF 动态轨迹。
- WGS84 椭球法向仰角与地表足印；球面近似锥体。
- 三个金融站点与伦敦—东京航线97点的即时接入计数。
- **仅几何：未考虑机械指向、光学误差、真实波束、天气、地形或容量。** 绿点不代表端到端网络已连通。

## 2. 网络时延模拟

使用相同的配置文件。网页提供本机运行的几何快算，Python 保留现有工程约束模型。

| 模式 | 计算范围 |
|---|---|
| 网页 / Python `geometry` | 拓扑、地面仰角、大气边界、星间距离、最短路径、传播与处理开销；可见星地链路即时就绪 |
| Python `engineering` | 以上及 FOV、LVLH 标称指向、转速、多普勒、星间捕获、地面一/双天线与 Make-Before-Break |

工程参数为抽象假设，尚无厂商误差标定、真实光链路预算、天气、容量、队列和因果包级传播。

输出 RTT 时序、路径、可用率、最长中断、在线 P99 与 P99−P1。RTT 是 **2×同一快照对称 OWTT**；P99−P1 是时延跨度，不是包间抖动。中断保留为缺失时延。有限采样100%不是永久连续服务证明。

## 本地安装和启动

Python 3.11+。无需下载实时星历、无需 Cesium ion token。网页的 CesiumJS 与底图从 CDN 加载，需要联网。

```sh
git clone https://github.com/carolplay/constellation-latency-lab.git
cd constellation-latency-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/build_site.py
python scripts/serve_tools.py
```

打开 `http://127.0.0.1:8766`，进入两项工具。构建只导出已有配置的星历并携带缓存统计，**不重跑研究扫描**。

```sh
# 工具1：CZML、几何接入 CSV 和统计
constellation-cover --config configs/candidate72.json --out outputs/my-coverage

# 工具2：与网页相同的几何口径
constellation-latency --config configs/candidate72.json \
  --mode geometry --out outputs/my-network

# 工具2：现有工程约束与切星状态机
constellation-latency --config configs/candidate72.json \
  --mode engineering --out outputs/my-engineering
```

`outputs/` 是本机运行结果，不纳入版本控制。可选依赖：`pip install -e '.[tle]'` 使用离线 SGP4/TLE；`.[public_models]` 提供 SciPy；`.[notebook]` 提供 Jupyter 环境。

## 输入配置和预设

详见 [共用配置规范](docs/tool-guide.md#共用配置schema_version1)。`configs/` 中有18/36/72星候选、Globalstar历史48星及Lightspeed2020年298星双层重建。

轨道层的 `pattern` 为 `delta`、`star` 或 `partial`。`grid` 拓扑每层最多四邻居、无跨层边；`complete` 是无限终端的乐观选边，最多150星。网页支持≤500星、≤20000快照、≤7天；Python核心另外保留逐星六要素与离线 TLE 接口。

新增参数无需修改源码，直接使用网页表单或配置JSON。要加入公共预设目录，添加 `configs/<id>.json` 与 `data/catalog.json`；覆盖统计需要真实计算结果及口径，不能填写假定100%。

## 目录

```text
configs/               共用 JSON 输入与已使用的方案
data/                  坐标、情景基准、预设目录和缓存统计
hftsim/                Python 轨道、几何、工程约束、路由和工具入口
viewer/                两项网页工具与浏览器几何计算模块
scripts/build_site.py  可复现静态站点构建
scripts/serve_tools.py  本地预览
tests/                 物理、配置、模型边界及浏览器/Python一致性检查
docs/                  工具说明与已有研究报告
examples/              已有研究的少量图表和摘要
```

研究已经停止扩大参数扫描。历史结果：[轨道布局比较](docs/constellation-tradeoffs.md)、[Globalstar与Lightspeed复现](docs/public-constellations-study.md)。它们是理想化重建，不是运营商实测或当前在轨舰队。东京为城市代理坐标；58.9/155/7.97ms地面基准为情景输入。

## 验证

```sh
pip install -e '.[tle]'
python -m unittest discover -s tests
node tests/browser-model.mjs
```

29项 Python 检查通过；浏览器几何核心对照Python的1254个位置及三种短区间路由结果通过。Node 22+，无需 npm 依赖。可选网页交互检查使用Playwright，脚本为 `scripts/verify_release_site.cjs`，只验证工具功能，不扩展星座研究。

## 性能

当前 Cesium 足印采用逐星 WGS84 边界求根与动态 Entity 绘制；较多卫星时可能卡顿。性能改造作为下一项工作，当前版本没有宣称72星已经流畅。可以先关闭足印/锥体，只显示轨迹。

发布后已记录 [72星渲染基线与建议](docs/performance.md)，没有修改模型或开始新一轮星座扫描。

## 许可

MIT。CesiumJS 使用 Apache-2.0；保留其可见署名。见 [NOTICE.md](NOTICE.md)。本仓库不含账户凭据、Site托管身份、用户粘贴原文或本机环境。
