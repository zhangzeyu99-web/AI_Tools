# 🌍 UI Localizer - 本地化小助手

> 多语言游戏 UI 本地化智能审计工具，支持截图分析和进化学习

## ✨ 功能特性

- 🌐 **多语言支持** - 支持 9 种目标语言：英语、德语、法语、土耳其语、西班牙语、葡萄牙语、俄语、日语、韩语
- 🤖 **AI 驱动** - 基于 Google Gemini 的本地化质量分析
- 📸 **截图分析** - 支持 UI 截图上传，自动识别截断、重叠等问题
- 🧠 **进化记忆** - 自动学习和记忆历史审计结果，持续优化
- 📚 **术语管理** - 内置术语表支持，确保翻译一致性
- 📊 **批量处理** - 支持大规模本地化文件批量审计
- 🎯 **精准分类** - 智能分类问题类型：
  - [Truncation] - 文本截断/重叠
  - [Untranslated] - 未翻译文本
  - [Grammar/Spelling] - 语法拼写错误
  - [Style/Tone] - 风格/语气不当
  - [Consistency] - 术语不一致

## 🚀 使用方法

### 1. 安装依赖

```bash
pip install customtkinter google-generativeai opencv-python pillow
```

### 2. 运行工具

```bash
python ui_localizer.py
```

### 3. 配置

首次运行会自动创建 `config.json`：
```json
{
  "api_key": "你的 Gemini API Key",
  "model": "gemini-2.5-flash",
  "target_language": "English"
}
```

### 4. 使用流程

1. 设置 API Key 和目标语言
2. 加载术语表（glossary.txt）
3. 选择待审计的文本或截图
4. 启动 AI 审计
5. 查看详细报告和改进建议

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `ui_localizer.py` | 主程序 |
| `config.json` | 配置文件 |
| `glossary.txt` | 术语表 |
| `history_db.json` | 历史审计数据库 |
| `evolution_memory.json` | 进化学习记忆 |
| `check_models.py` | 模型检查工具 |
| `history/` | 历史版本存档 |

## 🎯 模型选择

支持以下 Gemini 模型：
- `gemini-3-flash-preview` - 快速处理
- `gemini-3-pro-preview` - 高质量分析
- `gemini-2.5-flash` - 平衡选择

## 🔧 高级功能

- **视频支持** - 自动检测视频时长和帧提取
- **密度模式** - 高密度文本区域优化处理
- **提示词优化** - 内置专业本地化审计 Prompt

---
*版本: v15.0 | 更新时间: 2026-02-28*