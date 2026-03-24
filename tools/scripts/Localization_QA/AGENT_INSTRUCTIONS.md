# 游戏本地化质检工具 — Agent 操作指令

## 你是谁

你是一个自动化 Agent，负责使用本地化质检工具处理游戏语言包。你需要完成三个步骤：机审、AI审查、合并结果。

## 工具位置

```
C:\Users\Administrator\Desktop\localization-workflow-project\cli.py
```

## 完整操作流程

### 第一步：机审 + 生成 AI 提示词

运行以下命令（根据实际文件路径替换）：

```bash
python "C:\Users\Administrator\Desktop\localization-workflow-project\cli.py" \
  --input "语言表.xlsx" \
  --term-base "术语表.xlsx" \
  --auto-fix \
  --agent prepare \
  --output-dir "C:\Users\Administrator\Desktop\localization-workflow-project\output"
```

参数说明：
- `--input`：必填，语言表 Excel 文件路径
- `--term-base`：可选，术语库文件路径（Excel 或 JSON）
- `--auto-fix`：建议加上，自动修复能修的问题
- `--batch-size`：可选，200/500/1000，默认 500。根据语言表行数选择：
  - < 300 行：用 500（一批搞定）
  - 300~1000 行：用 500
  - > 1000 行：用 1000（减少批次数）
- `--agent prepare`：固定参数，表示非交互模式

命令完成后会生成：
- `output/result_en.xlsx` — 机审结果
- `output/report_en.xlsx` — 质检报告
- `output/ai_review/batch_1.txt` — 第1批AI审查提示词
- `output/ai_review/batch_2.txt` — 第2批（如有）
- ...

### 第二步：逐个读取提示词文件，发给 LLM，保存回复

**遍历** `output/ai_review/` 目录下所有 `batch_N.txt` 文件（N 从小到大）：

对每个 `batch_N.txt`：

1. **读取**文件的全部内容（这就是完整的提示词，包含术语表和待审查数据）
2. **把文件内容作为 prompt 发给 LLM**（你自己就是 LLM，直接处理即可）
3. **按照提示词中的规则回复**：
   - 只列出需要修改的行
   - 格式严格为：`ID | 修正版译文`
   - 没有问题的行不要列出
   - 如果全部没问题，回复 `无需修改`
4. **把你的回复保存为** `batch_N_response.txt`（放在同一目录下）

示例：
```
# 读取
prompt = read("output/ai_review/batch_1.txt")

# 你自己处理这个 prompt，生成回复

# 保存回复
write("output/ai_review/batch_1_response.txt", your_response)
```

**回复文件格式示例**（`batch_1_response.txt` 的内容）：

```
8 | An item worth [color =#dc6c00]10000[/color] Gems as a reward
9 | An item worth [color =#dc6c00]15000[/color] Gems as a reward
42 | Complete government missions for huge bounties! Activate the Electromagnetic Trap and eliminate the High-Risk Target
```

或者如果该批次没有问题：

```
无需修改
```

### 第三步：合并 AI 结果

所有 response 文件写完后，运行：

```bash
python "C:\Users\Administrator\Desktop\localization-workflow-project\cli.py" \
  --input "语言表.xlsx" \
  --term-base "术语表.xlsx" \
  --auto-fix \
  --agent merge \
  --output-dir "C:\Users\Administrator\Desktop\localization-workflow-project\output"
```

命令完成后，`output/result_en.xlsx` 和 `output/report_en.xlsx` 就是最终的质检结果。

## 关键注意事项

1. **第一步和第三步的 --input 和 --term-base 路径必须一致**，因为 merge 需要重跑机审来恢复内部状态
2. **response 文件命名必须对应**：`batch_1.txt` → `batch_1_response.txt`，`batch_2.txt` → `batch_2_response.txt`
3. **回复格式必须是 `ID | 修正版译文`**，每行一条，ID 是数字
4. **不需要修改的行不要写进 response**，否则会被当作"修正"覆盖原文
5. 如果某个 batch 你来不及处理或想跳过，不创建对应的 response 文件即可，merge 会自动忽略
6. 所有文件编码使用 **UTF-8**

## 快速判断批次大小

```
语言表行数    建议 --batch-size
< 500        500（一批搞定）
500~1500     500（2~3批）
> 1500       1000（减少批次）
```

## 出错处理

- 如果 prepare 报错"文件不存在"：检查 --input 和 --term-base 的路径
- 如果 merge 报错"ai_review 目录不存在"：说明没有先跑 prepare
- 如果 merge 报"未找到 response 文件"：说明第二步没有生成 response 文件，会只输出机审结果
