# MinerU 安装指南（实操 + 避坑）

> 面向用户/运维的实操安装指南。设计原理见 [development/mineru-install-design.md](development/mineru-install-design.md)。
> 这份文档把实际踩过的坑都列出来，照着装能一次成功，不用重走弯路。

## 版本约束（关键！不按这个一定冲突）

| 组件 | 必须版本 | 原因 |
|---|---|---|
| Python | **3.10–3.12** | mineru 依赖 ray，**Windows 不支持 3.13** |
| mineru | 3.4.0（最新，`<4`） | kbprep pyproject 约束 |
| torch | **2.8.0+cu126** | lmdeploy 0.11.1 要求 `torch==2.8.0`；cu126 既满足版本又提供 CUDA |
| lmdeploy | **0.11.1**（mineru[all] 自带，勿升级） | mineru 3.4.0 约束；升到 0.13 会 API 不兼容 |

**最重要一句话**：torch 必须是 **2.8.0+cu126**——不能是最新（2.12，和 lmdeploy 冲突），也不能是 CPU 版（GPU 用不上）。

## 三大坑（实测踩过，别再踩）

### 坑 1：不要裸 `pip install mineru[all]`
Windows 上 PyPI 的 torch 默认是 **CPU 版**。裸装 mineru[all] 会拉 CPU torch → GPU 用不上。
**正确**：用 `kbprep setup-env install_mineru=true`（内部先装 cu126 torch 再装 mineru[all]，顺序对）。

### 坑 2：torch 不要装 cu126 最新（2.12）
lmdeploy 0.11.1 要求 `torch==2.8.0`。装 cu126 最新（2.12）→ pip 装 lmdeploy 时为满足约束把 torch 降级成 CPU 版 → CUDA 丢失。
**正确**：锁 torch 2.8.0+cu126（`setup_env.py` 的 `CUDA_TORCH_PACKAGES` 已锁）。

### 坑 3：lmdeploy 不要单独升级
mineru 3.4.0 要 lmdeploy 0.11.1（有 `vl_async_engine` 模块）。单独 `pip install lmdeploy` 会拉最新 0.13 → 该模块没了 → mineru 报 `Please install lmdeploy`。
**正确**：保持 mineru[all] 装的 lmdeploy 0.11.1，永远别单独 `pip install lmdeploy`。

## Windows + lmdeploy turbomind：CUDA DLLs（不用装 3GB toolkit）

lmdeploy turbomind（hybrid/VLM 高精度模式）运行时要 `CUDA_PATH/bin` 下的 CUDA runtime DLLs。**重点：不用装 3GB 的 CUDA toolkit**——kbprep 的 `mineru_adapter._ensure_cuda_stub()` 会自动从 `torch/lib` 镜像 CUDA DLLs 到 `site-packages/cuda_stub/bin` 并设 `CUDA_PATH`。

- 这个 stub 是**全自动**的（mineru_adapter 调 mineru 时建，已存在则跳过）。
- 只 Windows + 用 lmdeploy（hybrid/VLM）时需要。pipeline（OCR）模式不需要。

## 正确安装步骤（一键）

```bash
# 1. setup-env 一键装（检测硬件 → cu126 torch 2.8.0 → mineru[all] → 后端建议）
node scripts/python-venv.mjs -m kbprep_worker.cli setup-env --json-stdin <<EOF
{"install_mineru": true}
EOF

# 2. preflight 验证（mineru + GPU + CUDA）
node scripts/python-venv.mjs -m kbprep_worker.cli preflight --json-stdin <<EOF
{"workdir": "./.kbprep/check"}
EOF
```

## 三套运行模式

| 模式 | CLI | 引擎 | 速度 | 用途 |
|---|---|---|---|---|
| pipeline OCR | `-b pipeline` | onnxruntime | 快（CPU 友好）| 扫描件、轻量任务（**kbprep 当前默认**）|
| hybrid transformers | `-b hybrid-engine` | transformers | 慢（~13秒/页）| 复杂版面，GPU 稳 |
| hybrid turbomind | `-b hybrid-engine` | lmdeploy turbomind | **快 9-13 倍**（多页）| 复杂版面，GPU 高速 |

首次运行自动下模型（国内用 modelscope 源，`MINERU_MODEL_SOURCE=modelscope`，快且不被墙）：
- pipeline OCR：PDF-Extract-Kit-1.0（表格/版面/OCR 全套）。
- hybrid/VLM：MinerU2.5-Pro-2605-1.2B。

## 硬件要求（MinerU 官方）

- GPU：NVIDIA Volta+ 或 Apple Silicon（pipeline 纯 CPU 也能跑）。
- 显存：pipeline ≥4GB，vlm/hybrid ≥8GB。
- RAM：≥16GB（推荐 32GB）。
- 磁盘：≥20GB。
- Python：3.10–3.12（**Windows 不含 3.13**，因 ray）。

## 重装/修复速查

如果环境坏了（torch 被降级/lmdeploy 错版本），按顺序修复：
```bash
# 1. 装/锁 lmdeploy 0.11.1
node scripts/python-venv.mjs -m pip install "lmdeploy==0.11.1"
# 2. force-reinstall torch 2.8.0 cu126（覆盖被降级的 CPU torch）
node scripts/python-venv.mjs -m pip install torch==2.8.0 torchvision==0.23.0 \
  --index-url https://download.pytorch.org/whl/cu126 --force-reinstall
# 3. 验证 torch CUDA + lmdeploy
node scripts/python-venv.mjs -c "import torch,lmdeploy;print(torch.cuda.is_available(),torch.__version__,lmdeploy.__version__)"
```
期望输出：`True 2.8.0+cu126 0.11.1`。
