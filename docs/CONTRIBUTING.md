# 📖 AI Tools 使用指南

## 目录

1. [工具分类说明](#工具分类说明)
2. [如何添加新工具](#如何添加新工具)
3. [文档规范](#文档规范)

---

## 工具分类说明

### 🌐 Web 应用工具 (`tools/web-tools/`)

基于浏览器的 AI 应用，包括：
- 网页版 AI 助手
- 在线数据处理工具
- Web 可视化界面

**技术栈建议**: HTML/CSS/JS, React, Vue

### 📜 脚本工具 (`tools/scripts/`)

自动化脚本，包括：
- 数据处理脚本
- 自动化工作流
- 批处理工具

**技术栈建议**: Python, Node.js, Bash

### 🔌 Chrome 扩展 (`tools/chrome-extensions/`)

浏览器扩展程序：
- 网页内容增强
- AI 辅助浏览工具
- 生产力工具

**技术栈建议**: JavaScript, Manifest V3

### 💻 CLI 工具 (`tools/cli-tools/`)

命令行工具：
- 终端 AI 助手
- 文件处理工具
- 开发辅助工具

**技术栈建议**: Node.js, Python, Go, Rust

---

## 如何添加新工具

### 1. 选择分类

根据工具类型，选择对应的目录：
```
tools/
├── web-tools/         ← Web 应用
├── scripts/           ← 脚本工具
├── chrome-extensions/ ← Chrome 扩展
└── cli-tools/         ← 命令行工具
```

### 2. 创建工具目录

```bash
mkdir tools/web-tools/my-new-tool
cd tools/web-tools/my-new-tool
```

### 3. 添加必要文件

每个工具必须包含：

```
my-new-tool/
├── README.md          # 工具说明文档（必需）
├── LICENSE            # 开源协议（建议 MIT）
├── src/               # 源代码目录
│   └── ...
├── examples/          # 使用示例
│   └── ...
└── package.json       # 依赖清单（Node.js 项目）
```

### 4. 编写 README

工具 README 模板：

```markdown
# 工具名称

> 一句话描述工具功能

## 功能特性

- ✅ 特性 1
- ✅ 特性 2
- ✅ 特性 3

## 安装

```bash
# 安装命令
```

## 使用方法

```bash
# 使用示例
```

## 配置说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| xxx | string | - | 参数说明 |

## 更新日志

### v1.0.0 (2026-02-28)
- 🎉 初始版本发布

---
*创建于 2026-02-28*
```

### 5. 更新主 README

在仓库根目录的 `README.md` 中，将工具添加到对应分类的表格中。

### 6. 提交代码

```bash
git add .
git commit -m "添加工具: [工具名称]

- 功能描述
- 技术栈
- 其他说明"
git push origin main
```

---

## 文档规范

### 命名规范

- **目录名**: 小写字母，短横线连接，如 `ai-image-generator`
- **文件名**: 小写字母，描述清晰，如 `main.js`, `README.md`
- **变量名**: 遵循对应语言的命名规范

### 代码规范

- 添加适当的注释
- 保持代码简洁易读
- 处理异常情况
- 不要提交敏感信息（API keys, 密码等）

### 提交规范

提交信息格式：
```
类型: 简短描述

详细说明（可选）
```

类型包括：
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 其他杂项

---

有问题？联系维护者！ 🦐