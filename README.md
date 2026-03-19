# 🤖 AI Tools - 个人工具库

> 实用的 AI 辅助工具，提升工作效率

## 🛠️ 工具清单

| 工具 | 功能 | 核心文件 |
|------|------|----------|
| **LQA Master** | 游戏本地化质量审计 | [`lqa_tool.py`](tools/scripts/LQA_Master/lqa_tool.py) |
| **UI Localizer** | 多语言 UI 视频审计 | [`ui_localizer.py`](tools/scripts/LQA_Tool/ui_localizer.py) |
| **帮我填写** | 工作日报自动填写 | [`todo_gui.py`](tools/scripts/帮我填写/todo_gui.py) |
| **Localization QA** | 游戏本地化质检工作流 | [`gui.py`](tools/scripts/Localization_QA/gui.py) |

---

## 🚀 快速开始

每个工具都是**单个 Python 文件**，开箱即用：

### 1. 安装 Python
- 访问 https://www.python.org/downloads/
- 下载 Python 3.10+
- ⚠️ **安装时勾选** "Add Python to PATH"

### 2. 安装依赖

**LQA Master:**
```bash
pip install pandas google-generativeai customtkinter
```

**UI Localizer:**
```bash
pip install customtkinter google-generativeai opencv-python pillow
```

**帮我填写:**
```bash
pip install --upgrade openai google-genai selenium
```

**Localization QA:**
```bash
pip install pandas openpyxl
```

### 3. 获取 API Key

| 工具 | 推荐模型 | 申请地址 |
|------|----------|----------|
| LQA Master | Gemini | https://aistudio.google.com/app/apikey |
| UI Localizer | Gemini | https://aistudio.google.com/app/apikey |
| 帮我填写 | DeepSeek | https://platform.deepseek.com |
| Localization QA | ChatGPT (网页版) | 无需 API Key |

### 4. 运行工具

```bash
python lqa_tool.py        # LQA Master
python ui_localizer.py    # UI Localizer
python todo_gui.py        # 帮我填写
python gui.py             # Localization QA（在 Localization_QA 目录下运行）
```

---

## 📖 详细说明

每个 Python 文件头部都包含**完整的安装使用说明**，打开文件即可查看：

```python
"""
==============================================================================
📦 安装步骤
==============================================================================
...

==============================================================================
🚀 使用方法
==============================================================================
...
"""
```

---

## ⚠️ 免责声明

本工具仅作为效率辅助，AI 生成内容可能存在误差，请务必人工复核后使用。
用户需自行承担使用风险。

---

*更新时间: 2026-03-19*