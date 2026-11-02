# 第三方来源与授权范围

本次整理没有改变原文件中的版权声明，也不将他人的代码声明为自研。

| 部分 | 来源 / 说明 |
|---|---|
| FPGA DDR、PCIe、MIPI、ISP 与板级设计 | 原工程采用安路 TD 生成的 IP 和 AFC03 / 米联客参考工程；部分文件含加密内容及厂商版权声明。原头部保留，使用范围遵循相应厂商协议；本仓库未额外授予再许可权。 |
| PCIe / V4L2 Linux 驱动 | 原厂驱动基础上的工程修改；保留源文件 GPL 等声明。需要与板端 Linux 6.1.99 BSP 配套。 |
| Screened Poisson 13.72 | Michael Kazhdan 等，来源 https://www.cs.jhu.edu/~misha/Code/PoissonRecon/Version13.72/ 。完整版权/许可见 `rk/poisson/AdaptiveSolvers/LICENSE`；此处包括样机采用的编译适配。 |
| Vue、Three.js、Vite | 不复制 node_modules，版本及依赖树由前端 package-lock.json 记录；各依赖遵守各自许可证。 |
| NumPy、SciPy、OpenCV、FastAPI、Trimesh、scikit-image 等 | 不复制安装包；核心运行版本见 `rk/requirements.txt`，需按各项目许可安装。 |
| 色彩参考 | 拓竹目录色号 HEX、文档中注明的社区 RFID 读出；不是标准反射率或经仪器测量的 Lab 数据。参考来源见颜色配置及 orange-reference-provenance.json。 |

未选定整个项目的统一开源许可证。需要再分发或商用时，应分别遵循对应文件的授权条件。

## 2026-10-12 新增部分

- 陈列馆附带的 Three.js 浏览器模块许可证位于 `museum/vendor/LICENSE`；npm 依赖由两个前端各自的 package-lock.json 固定。
- 界面字体授权声明在 `rk/rootfs/opt/afc03-scanner/frontend/src/assets/fonts/` 与 `museum/src/assets/fonts/`，浏览器可访问的声明亦随 public 素材保留。各字体遵守原授权，不统一改为项目许可。
- RKNN Toolkit2 / Lite2 来自 Rockchip 官方 `airockchip/rknn-toolkit2` v2.3.2。仅提交项目模型、转换脚本、下载来源及校验记录，未提交 SDK 安装包或系统运行库。
