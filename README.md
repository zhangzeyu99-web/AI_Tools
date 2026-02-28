# 🤖 AI Tools 工具库

[![GitHub Repo](https://img.shields.io/badge/GitHub-AI__Tools-blue?logo=github)](https://github.com/zhangzeyu99-web/AI_Tools)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Last Updated](https://img.shields.io/badge/Last%20Updated-2026--02--28-green)]()

> 个人制作的 AI 工具合集，持续更新中...

## 📂 仓库结构

```
AI_Tools/
├── 📁 tools/                  # 工具目录
│   ├── 📁 web-tools/         # Web 应用工具
│   ├── 📁 scripts/           # 脚本工具
│   ├── 📁 chrome-extensions/ # Chrome 扩展
│   └── 📁 cli-tools/         # 命令行工具
├── 📁 docs/                   # 文档说明
├── 📁 examples/               # 使用示例
└── 📄 README.md              # 本文件
```

## 🛠️ 工具清单

### 📜 脚本工具 (`tools/scripts/`)

| 工具名称 | 描述 | 技术栈 | 状态 |
|---------|------|--------|------|
| [LQA Master](tools/scripts/LQA_Master/) | 游戏本地化 LQA 审计工具 | Python + Gemini API | ✅ |
| [LQA Tool](tools/scripts/LQA_Tool/) | UI 本地化助手（多语言支持） | Python + Gemini API + CV | ✅ |
| [帮我填写](tools/scripts/帮我填写/) | 工作日报自动填写助手 | Python + OpenAI + Selenium | ✅ |

### 🌐 Web 应用工具

| 工具名称 | 描述 | 链接 | 状态 |
|---------|------|------|------|
| *(待添加)* | - | - | 📝 |

### 🔌 Chrome 扩展

| 工具名称 | 描述 | 链接 | 状态 |
|---------|------|------|------|
| *(待添加)* | - | - | 📝 |

### 💻 CLI 工具

| 工具名称 | 描述 | 命令 | 状态 |
|---------|------|------|------|
| *(待添加)* | - | - | 📝 |

## 🎯 工具详情

### 🎮 LQA Master
基于 Gemini AI 的游戏本地化质量审计工具，支持 Excel 批量处理和术语一致性检查。

**核心功能：**
- AI 自动化翻译质量审计
- 术语表支持
- 多维度错误检测
- 友好 GUI 界面

[查看详情 →](tools/scripts/LQA_Master/)

---

### 🌍 UI Localizer (本地化小助手)
多语言游戏 UI 本地化智能审计工具，支持截图分析和进化学习。

**核心功能：**
- 9 种语言支持
- UI 截图分析
- 进化记忆系统
- 批量处理能力

[查看详情 →](tools/scripts/LQA_Tool/)

---

### 📝 帮我填写
自动化填写工作日报的智能工具，基于 AI 生成内容并自动填充。

**核心功能：**
- AI 智能生成日报
- 自动网页填充
- 关键词驱动
- 历史记录管理

[查看详情 →](tools/scripts/帮我填写/)

## 🚀 快速开始

### 安装依赖

```bash
# 克隆仓库
git clone https://github.com/zhangzeyu99-web/AI_Tools.git
cd AI_Tools

# 进入具体工具目录安装依赖
cd tools/scripts/LQA_Master
pip install -r requirements.txt  # 如果有
```

### 使用工具

每个工具都有独立的 README 说明，进入对应目录查看详细文档：

```bash
cd tools/scripts/LQA_Master
python lqa_tool.py
```

## 📖 贡献指南

### 添加新工具

1. 在 `tools/` 下创建对应分类的文件夹
2. 添加工具代码和 `README.md`
3. 在主 README 中更新工具清单
4. 提交 PR 或直接推送

### 工具规范

每个工具应包含：
- ✅ `README.md` - 使用说明文档
- ✅ `LICENSE` - 开源协议（建议 MIT）
- ✅ 示例代码或演示
- ✅ 依赖清单（`package.json` / `requirements.txt` 等）

详细规范请查看 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)

## 📝 更新日志

### 2026-02-28
- 🎉 仓库初始化
- 📚 创建基础目录结构和 README
- 🎮 添加 **LQA Master** - 游戏本地化审计工具
- 🌍 添加 **UI Localizer** - 多语言本地化助手
- 📝 添加 **帮我填写** - 工作日报自动助手

---

*由 小虾 维护管理* 🦐