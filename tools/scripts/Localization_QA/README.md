# 🌐 Localization QA - 游戏本地化质检工作流

> 机审 + AI审 两遍质检，自动化处理 AI 粗翻后的游戏语言包

## ✨ 功能特性

- 🔍 **变量完整性检查** - 检测 `{icon1}`、`{num1}` 等变量是否缺失/多余
- 🏷️ **BBCode 标签检查** - 验证 `[color=#dc6c00]...[/color]` 标签闭合与颜色值一致性
- 📖 **术语一致性** - 对照术语库（Excel/JSON），检查标准术语是否使用、大小写是否正确
- 🔄 **句式一致性检测** - 同模板的译文必须使用相同句式（核心功能）
- 🈲 **中文残留检测** - 检测译文中遗留的中文字符
- 📱 **UI 文本识别** - 自动判断短文本/按钮类 UI 文本
- 🤖 **AI 深度审校** - 分批发送给 ChatGPT 做二次审查（错译/漏译/不自然表达）
- 🔧 **自动修复** - 变量补全、术语大小写修正、句式统一
- 🖥️ **友好 GUI** - 两阶段可视化界面，剪贴板引导 AI 审查流程

## 🚀 使用方法

### 1. 安装依赖

```bash
pip install pandas openpyxl
```

### 2. 运行工具

```bash
python gui.py
```

### 3. 使用流程

```
第一步 · 机审质检
├── 选择语言表 Excel（必需）
├── 选择术语库 Excel / JSON（可选）
├── 勾选"自动修复"
└── 点击「开始机审」

第二步 · AI审查
├── 点击「复制提示词」→ 自动复制到剪贴板
├── 点击「打开 ChatGPT」→ 浏览器打开
├── 粘贴提示词到 ChatGPT，等待回复
├── 复制 AI 回复
├── 点击「粘贴AI结果」→ 自动解析修正
├── 重复以上步骤直到所有批次完成
└── 点击「完成AI审查」→ 生成最终文件
```

## 📋 输入格式

### 语言表 Excel（必需）

| 列 | 字段 | 示例 |
|----|------|------|
| A | ID | 1, 2, 3... |
| B | 原文 | 充值积分达到{icon1}[color=#dc6c00]{num1}[/color] |
| C | 译文 | Top-up Points reaching {icon1}[color=#dc6c00]{num1}[/color] in total |

### 术语库（可选）

支持 **Excel**（与语言表相同格式：ID / 原文 / 译文）或 **JSON**：

```json
{
  "机甲战士": "Mech Warrior",
  "宝石": "Gems"
}
```

## 📝 输出结果

### result_{lang}.xlsx（结果文件，2个Sheet）

| Sheet | 内容 |
|-------|------|
| 完整结果 | 全量数据，格式 = 输入格式 + 备注列（修改原因） |
| 需确认 | 需人工审阅的子集，含 AI 建议、置信度、原因 |

### report_{lang}.xlsx（质检报告，4个Sheet）

| Sheet | 内容 |
|-------|------|
| 总览 | 统计数字（总行数/自动修复/需确认/无改动/UI文本数） |
| 错误模式 | 错误类型、数量、示例 ID、描述 |
| 学习笔记 | 发现的语言规律（用于自我进化） |
| 详细记录 | 每条修改的 ID / 原文 / 修改前 / 修改后 / 原因 |

## 🔧 命令行使用

除 GUI 外，也支持命令行直接运行（仅机审）：

```bash
python process_language.py --input language.xlsx --auto-fix
python process_language.py --input language.xlsx --term-base terms.xlsx --lang en --auto-fix
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--input` | ✅ | 语言表 Excel 路径 |
| `--term-base` | ❌ | 术语库文件路径（Excel 或 JSON） |
| `--lang` | ❌ | 语言代码，默认 `en` |
| `--output-dir` | ❌ | 输出目录，默认 `./output/` |
| `--auto-fix` | ❌ | 开启自动修复 |

## 🧠 核心算法

### 句式一致性检测

同模板的中文原文（如"获得后，可解锁___头像"），对应的英文译文必须用相同句式。

**算法：**
1. 对中文原文做"结构指纹"——保留首尾锚点字符，中间名词替换为长度分桶占位符
2. 相同指纹的行归为一组
3. 对每组英文译文，识别槽位词（专有名词），生成结构模板
4. 统计最常见模板，标记不一致项

**示例：**
```
ID 752: 获得后，可解锁阿力斯特头像 → Unlocks the Alistair Avatar when obtained
ID 753: 获得后，可解锁艾丽莎头像   → Once obtained, unlocks the Elisa Avatar     ✅
ID 754: 获得后，可解锁未来战士头像 → Unlocks the Austin Avatar after obtaining   ❌ 不一致
```

### AI 审查分批处理

大文件自动拆分为 200 行/批，逐批送给 AI 审校：
- 提示词包含检查维度（错译/漏译/代码错误/术语不统一）
- AI 返回 `ID | 修正版译文` 格式
- 脚本自动解析并应用修正
- 支持「上一批」撤回重做

## 📁 文件结构

```
Localization_QA/
├── gui.py                    # GUI 入口
├── process_language.py       # 核心质检脚本（CLI + GUI调用）
├── requirements.txt          # 依赖（pandas + openpyxl）
├── utils/
│   ├── excel_reader.py       # Excel 读取（支持单/多语言列）
│   ├── variable_checker.py   # 变量 + BBCode 标签检查
│   ├── term_checker.py       # 术语命中 + 语法校验
│   ├── pattern_detector.py   # 句式一致性检测
│   ├── ui_detector.py        # UI 文本识别
│   └── ai_checker.py         # AI 审校（分批 + 提示词 + 解析）
└── output/                   # 输出目录
```

## ⚠️ 注意事项

- 当前优先支持**英语（P0）**，核心逻辑语言无关，可扩展至其他语言
- AI 审查使用 ChatGPT 网页版（通过剪贴板），无需 API Key
- 术语库由用户手动维护，脚本仅做对照检查
- 自动修复默认保守，高置信度才替换；不确定的标记为"需确认"

---

*创建时间: 2026-03-19*
