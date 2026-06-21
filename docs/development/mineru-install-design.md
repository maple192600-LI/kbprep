# MinerU 安装与环境检测设计

> 本文档定义 MinerU 在 KBPrep 里的安装规模选择、硬件检测、用户引导流程。它是 `docs/standalone-cli.md` Runtime Setup 的展开，不是新的开发阶段。

## 1. MinerU 在 KBPrep 的角色

MinerU 是 KBPrep PDF 三层路由的核心引擎：

- **Tier 2** `mineru_auto`：复杂排版 PDF（多栏、表格密集）。
- **Tier 3** `mineru_ocr`：扫描件、图片型 PDF（OCR）。
- 图片 OCR 路由 `image_to_pdf_then_mineru_ocr` 也走 MinerU。

因此 MinerU 是**必装核心依赖**（`python/pyproject.toml`: `mineru[all]>=3.2.1,<4`），不是可选。纯文本 PDF、Markdown、HTML、Office 等路由不依赖 MinerU，但 PDF 复杂/扫描转换离不开它。

## 2. 安装规模：全量 vs 推理后端

MinerU 的"规模"不是 pip extra 名，而是**推理后端**的选择：

| 后端 | 适用 | 纯 CPU | 最小显存 | 精度 |
|---|---|---|---|---|
| `pipeline` | 兼容性最好、批量稳定 | ✅ | 4GB | 高（OmniDocBench 86.47） |
| `vlm-engine`（vllm/sglang/lmdeploy/mlx） | 高精度、复杂版面 | ❌ | 8GB | 最高（95.39 high / 95.26 medium） |
| `hybrid-engine` | 高精度 + 原生文本抽取、低幻觉 | ❌ | 8GB | 最高 |
| `*-http-client` | 连远程 OpenAI 兼容服务 | ✅ | 2GB | 取决于远端 |

- **全量包**：`mineru[all]` 含所有核心功能（官方默认推荐，Win/Linux/Mac 通用）。
- **轻量**：在 `mineru[all]` 基础上按硬件选后端，或只装轻量客户端连远端服务（见 MinerU 官方 Extension Modules Installation Guide）。

## 3. 硬件要求（MinerU 官方，2026-06 核查）

| 项 | pipeline | *-engine | *-http-client |
|---|---|---|---|
| GPU 加速 | Volta 及以后架构 或 Apple Silicon | 同左 | 不需要 |
| 最小显存 | 4GB | 8GB | 2GB |
| RAM | ≥16GB（推荐 32GB） | 同左 | ≥16GB |
| 磁盘 | ≥20GB（推荐 SSD） | 同左 | ≥2GB |
| Python | 3.10–3.13 | 同左 | 同左 |

**Windows 限制**：关键依赖 `ray` 不支持 Windows 上的 Python 3.13，Windows 仅支持 Python 3.10–3.12。CUDA 加速装不上时查 MinerU 官方 Windows CUDA 加速 FAQ。

## 4. 安装流程：检测 + 选择 + 说明（目标设计）

首次安装走"先检测、再建议、用户选、最后装、装完验"五步，不允许裸 `pip install` 盲装：

1. **检测**（复用 `python/kbprep_worker/setup_env.py`）：`nvidia-smi`、torch/CUDA、显卡型号、显存、RAM、Python 版本、磁盘空间。
2. **建议后端**：
   - NVIDIA 显存 ≥8GB → 建议 `vlm-engine`/`hybrid-engine`（高精度）。
   - 显存 4–8GB 或无独显 → 建议 `pipeline`（兼容、可纯 CPU）。
   - 本地硬件不足但有远程服务 → 建议 `*-http-client`。
3. **用户选择 + 小白说明**：输出"你的显卡是 X、显存 Y GB、建议后端 Z、全量约 N GB、首次需下模型、大概 M 分钟、为什么"，让用户在全量/轻量/后端之间选。纯小白也能看懂。
4. **安装**：按选择装 `mineru[all]` + 对应后端依赖；CUDA torch 走 `setup_gpu` 的 cu126 流程（已有）。
5. **验证**（复用 `python/kbprep_worker/preflight.py`）：报告 mineru 可用 + 实际后端 + GPU/CUDA + 显存。

## 5. 现状（截至 2026-06-20）

**已有**：
- `python/kbprep_worker/setup_env.py`：硬件检测全套（`check_nvidia_driver`、`probe_torch` 含显卡型号+显存、`get_gpu_info`、`detect_device`、`setup_gpu` 自动装 cu126 torch，带 `device_override`/超时/失败处理）。
- `python/kbprep_worker/cli.py`：`setup-env` 命令 → `setup_gpu`。
- `python/kbprep_worker/preflight.py`：mineru 可用性 + torch/CUDA + GPU + warnings。
- `README.md` / `docs/standalone-cli.md` Runtime Setup：首次 4 步（建 venv → 升 packaging → 装 worker 依赖 → setup-env probe）。

**已实现**（2026-06-21）：
1. `setup-env` 检测后输出**建议后端 + 各后端说明 + 显存够不够**，支持 `backend_override` 让用户选（`setup_env.py`: `choose_mineru_backend` / `suggest_mineru_backend` / `mineru_backend_options`）。
2. 本文档（`docs/development/mineru-install-design.md`）。
3. **统一受控安装入口**：`setup-env` 支持 `install_mineru=true`，一步到位——检测硬件 → 装 cu126 torch（CUDA）→ 装 `mineru[all]` → 给后端建议。**禁止裸 `pip install mineru[all]`**：Windows 上 PyPI 的 torch 默认是 CPU 版，裸装会装错；必须先 cu126 torch 再 mineru[all]，`setup-env` 已按此顺序统筹。

**两条安装路径：**
- **开发轻量**：`scripts/python-venv.mjs`（dev venv 引导，只装 PyMuPDF/bs4/lxml + 工具，不装 mineru/torch）——用于本地开发、跑测试、CI。
- **全量（生产 / 老李机器）**：`kbprep_worker.cli setup-env` 传 `{"install_mineru": true}`——统筹装 cu126 torch + mineru[all]，GPU 自动检测并给后端建议。首次运行 mineru 时还要按需下 VLM/OCR 模型（几个 G）。

## 6. 许可证

MinerU 3.1.0（2026/04/18）起从 AGPLv3 改为 **MinerU 开源许可证（基于 Apache 2.0，含附加条件）**，允许商业使用，仅月活超 1 亿触发额外条款。对 KBPrep 及老李的使用场景无障碍。
