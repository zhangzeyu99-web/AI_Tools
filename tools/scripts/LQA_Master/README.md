# 🎮 LQA Master - 游戏本地化 LQA 审计工具

> 基于 Gemini AI 的游戏本地化质量自动化审计工具

## ✨ 功能特性

- 🤖 **AI 自动化审计** - 使用 Google Gemini API 智能分析翻译质量
- 📊 **Excel 支持** - 直接导入导出 Excel 文件进行批量处理
- 📚 **术语表支持** - 可加载自定义术语表进行一致性检查
- 🎯 **多维度检测**:
  - 语法和拼写错误
  - 术语一致性问题
  - 上下文适配问题
  - 风格/语气问题
- 📈 **进度可视化** - 实时进度条和日志输出
- 🖥️ **友好 GUI** - 基于 CustomTkinter 的现代化界面

## 🚀 使用方法

### 1. 安装依赖

```bash
pip install pandas google-generativeai customtkinter
```

### 2. 运行工具

```bash
python lqa_tool.py
```

### 3. 使用流程

1. 输入 Gemini API Key
2. 选择待审计的 Excel 文件
3. （可选）选择术语表文件
4. 点击"开始自动化审计"
5. 等待处理完成，查看结果

## 📋 输入格式

Excel 文件应包含以下列：
- 原文（Source）
- 译文（Translation）
- 上下文（Context）- 可选

## 🔧 配置说明

| 参数 | 说明 |
|------|------|
| API Key | Google Gemini API 密钥 |
| Excel 文件 | 待审计的本地化文件 |
| 术语表 | CSV 或 Excel 格式的术语对照表 |

## 📝 输出结果

审计完成后会生成：
- 详细的错误报告
- 问题分类统计
- 改进建议

## ⚠️ 注意事项

- 需要有效的 Gemini API Key
- 建议先使用小批量数据测试
- 术语表格式需符合工具要求

---
*创建时间: 2026-02-28*