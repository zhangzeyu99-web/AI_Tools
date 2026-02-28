#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
🌍 UI Localizer - 游戏本地化审计助手 (v15.0)
==============================================================================

📋 功能简介：
    多语言游戏 UI 本地化智能审计工具，支持视频分析和截图检测。
    自动识别 UI 溢出、拼写错误、中式英语(Chinglish)、用词不当。

✨ 主要功能：
    • 支持 9 种语言: 英/德/法/土/西/葡/俄/日/韩
    • 视频逐帧审计，自动检测 UI 问题
    • 进化记忆库，支持用户调教 AI
    • 术语一致性检查
    • Excel 友好输出格式

==============================================================================
📦 安装步骤
==============================================================================

1. 安装 Python (3.10+)
   访问 https://www.python.org/downloads/ 下载安装
   ⚠️ 安装时务必勾选 "Add Python to PATH"

2. 安装依赖库
   打开命令行 (cmd)，运行：
   
   pip install customtkinter google-generativeai opencv-python pillow

3. 获取 Gemini API Key
   • 访问 https://aistudio.google.com/app/apikey
   • 创建 API Key

==============================================================================
🚀 使用方法
==============================================================================

1. 启动软件
   在文件所在目录打开命令行，运行：
   
   python ui_localizer.py

2. 配置 API Key
   • 在界面顶部输入框填入 Gemini API Key
   • 选择模型 (推荐 gemini-3-pro-preview)

3. 导入视频
   • 点击"📂 导入视频"选择 MP4/MOV 文件
   • 选择处理模式: 标准 / 高密度

4. 开始分析
   • 点击"🔍 开始分析"
   • 等待状态栏显示完成

5. 导出结果
   • 点击"📋 复制 (Tab格式)"
   • 粘贴到 Excel (Ctrl+V)，自动分列

==============================================================================
🧬 进化记忆库 (调教 AI)
==============================================================================

1. 在界面找到"🧬 进化记忆库"区域
2. 点击"➕ 添加新规则"
3. 输入规则，例如：
   • "Recharge 必须改为 Top-up"
   • "不要把 Hero 翻译成 Champion"
   • "报错信息使用严肃语气"

==============================================================================
⚠️ 注意事项
==============================================================================

• 建议视频时长控制在 45 分钟以内，大小 < 2GB
• AI 识别并非全对，请注意甄别，主观判断
• 需要能连接 Google API 的网络环境

==============================================================================
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import google.generativeai as genai
import os
import time
import threading
import json
import re
import math
import difflib
import cv2
from datetime import datetime
from PIL import Image

# ==============================================================================
# ⚙️ 全局配置
# ==============================================================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "config.json"
HISTORY_DB_FILE = "history_db.json"
EVOLUTION_DB_FILE = "evolution_memory.json"
GLOSSARY_FILE = "glossary.txt"

TARGET_LANGUAGES = ["English", "German", "French", "Turkish", "Spanish", "Portuguese", "Russian", "Japanese", "Korean"]
MODEL_LIST = ["gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-2.5-flash"]

# ==============================================================================
# 🧠 核心 PROMPT
# ==============================================================================

SYSTEM_PROMPT = """
[Role & Objective]
You are a Senior Localization QA Director (LQA) auditing a video game.
Target Language: **{target_lang}**.
Your audience is native speakers who are extremely sensitive to unnatural phrasing, UI overflows, and context mismatches.

[Audit Standards - THINK BEFORE YOU LOG]
1. **Context is King**: Do not just check grammar. Check if the text fits the UI (is it cut off?) and fits the scene.
2. **Issue Categorization**: Use ONLY these categories:
   - [Truncation]: Text is cut off or overlaps with UI elements.
   - [Untranslated]: Text remains in the source language (CN/EN).
   - [Grammar/Spelling]: Typos, wrong capitalization, or basic errors.
   - [Style/Tone]: Grammatically correct but sounds unnatural/robotic in {target_lang}.
   - [Consistency]: Terminology does not match the glossary or previous context.

[Output Protocol - EXCEL STRICT MODE]
1. **Output ONLY valid rows**. No introductory text, no markdown tables, no code blocks.
2. **Delimiter**: Use a single TAB (\\t) between columns.
3. **Forbidden**: Do NOT use line breaks (\\n) inside a cell. Replace any line breaks within text with " | ".
4. **Header Row**: Time\\tLocation\\tIssue Type\\tOriginal Text\\tBetter {target_lang}\\tDeep Analysis (CN)

[Handling "No Issues"]
- If a segment has absolutely NO localization or UI issues, output NOTHING for that timestamp. Do not log "Pass" or "OK". Only log actionable errors.
"""

STANDARD_INIT_PROMPT = """
[Task]
Audit the video from **00:00** as far as you can.
- Include the Header Row at the very top.
- If you reach the end of the video, output "[END_OF_VIDEO]" at the last line.
"""

STANDARD_CONTINUE_PROMPT = """
[Task]
**Continue auditing exactly from {last_timestamp}**.
Do NOT repeat the Header Row.
If you reach the end of the video, output "[END_OF_VIDEO]" at the last line.
"""

DENSITY_SEGMENT_PROMPT = """
[STRICT TIMEFRAME]
Audit ONLY from **{start_time}** to **{end_time}**.

[Instruction]
1. Scan every visible UI element and dialogue subtitle.
2. If text is blurry or ambiguous, SKIP it. Do not guess.
3. If the issue is a "Style/Tone" preference, only log it if the original is clearly wrong.

[Header Rule]
{header_instruction}
"""

IMAGE_PROMPT_INIT = """
[角色]
你是一位资深游戏本地化专家(LQA)。
当前审计的目标语言是：**{target_lang}**。

[任务]
分析截图 UI 文本，进行LQA审计。
严格遵守术语表。

[输出规范]
1. **直接输出报告内容**，不要有任何开场白。
2. **Issue Type** 和 **Deep Analysis** 必须使用中文。

[格式模版]
【🕹️ 界面场景】...
【🔍 问题发现与优化 ({target_lang})】...
【🛠️ UX建议】...
"""

IMAGE_PROMPT_FOLLOWUP = """
[任务]
基于上下文和用户新指令修改报告。
用户指令: "{user_input}"
只输出修改后的内容或完整报告。
"""

REFLECTION_PROMPT = """
Analyze the user's complaint and extract a general rule.
Complaint: "{user_input}"
Output ONLY the rule sentence in English.
"""

# ==============================================================================
# 🏗️ 主程序类
# ==============================================================================

class VideoLocalizationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gemini 3 LQA Studio (Excel Pro v20.1)")
        self.geometry("1450x950")

        self.file_path = None
        self.image_path = None     
        self.ref_image_path = None 
        
        self.chat_session = None 
        self.session_api_key = None 
        
        self.history_data = []
        self.evolution_memory = [] 
        
        # 运行时去重记录
        self.dedup_records = []

        self._ensure_glossary_exists()
        self._init_ui()
        self._load_config()
        self._load_history_db()
        self._load_evolution_db()

    def _ensure_glossary_exists(self):
        if not os.path.exists(GLOSSARY_FILE):
            with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
                f.write("# 术语表\n# 示例: 羁绊 = Traits\n")

    def _init_ui(self):
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self.sidebar_frame, text="LQA 历史归档", font=("微软雅黑", 18, "bold")).grid(row=0, column=0, padx=20, pady=(20, 10))
        self.history_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="双击查看")
        self.history_list_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        ctk.CTkButton(self.sidebar_frame, text="🗑️ 删除记录", command=self.delete_current_history, fg_color="#D32F2F").grid(row=3, column=0, padx=20, pady=20)

        # --- Main Area ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        self._init_top_bar()

        self.tab_view = ctk.CTkTabview(self.main_frame)
        self.tab_view.pack(pady=10, padx=20, fill="both", expand=True)
        
        self.tab_video = self.tab_view.add(" 🎥 视频审计 (Excel) ")
        self.tab_image = self.tab_view.add(" 🖼️ 截图精修 ")

        self._init_video_ui(self.tab_video)
        self._init_image_ui(self.tab_image)

        self.progressbar = ctk.CTkProgressBar(self.main_frame, mode="indeterminate", width=800)
        self.progressbar.pack(pady=5, padx=20, fill="x")
        self.lbl_status = ctk.CTkLabel(self.main_frame, text="System Ready", text_color="silver")
        self.lbl_status.pack()

    def _init_top_bar(self):
        top_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        top_container.pack(fill="x", padx=20, pady=10)

        config_frame = ctk.CTkFrame(top_container)
        config_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(config_frame, text="API Key:").pack(side="left", padx=10)
        self.api_key_var = tk.StringVar()
        ctk.CTkEntry(config_frame, textvariable=self.api_key_var, show="*", width=200).pack(side="left", padx=5)
        
        self.model_combo = ctk.CTkComboBox(config_frame, values=MODEL_LIST, width=180)
        self.model_combo.set(MODEL_LIST[0])
        self.model_combo.pack(side="left", padx=10)

        ctk.CTkLabel(config_frame, text="Target:", text_color="#4DB6AC").pack(side="left", padx=(15, 5))
        self.lang_combo = ctk.CTkComboBox(config_frame, values=TARGET_LANGUAGES, width=140, state="readonly")
        self.lang_combo.set("English")
        self.lang_combo.pack(side="left", padx=5)

        right_frame = ctk.CTkFrame(top_container, fg_color="transparent")
        right_frame.pack(side="right")
        ctk.CTkButton(right_frame, text="📚 术语", command=self.open_glossary, width=80, fg_color="#5C6BC0").pack(side="left", padx=5)
        ctk.CTkButton(right_frame, text="🧠 进化", command=self.auto_learn_rule, width=80, fg_color="#FF9800", text_color="black").pack(side="right", padx=5)

    def _init_video_ui(self, parent):
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.pack(pady=10, fill="x")
        ctk.CTkButton(file_frame, text="📂 导入视频", command=self.select_video_file, width=120, fg_color="#444", hover_color="#555").pack(side="left")
        self.lbl_video_name = ctk.CTkLabel(file_frame, text="请先导入视频...", text_color="gray")
        self.lbl_video_name.pack(side="left", padx=15)
        
        # Controls
        ctrl_frame = ctk.CTkFrame(file_frame, fg_color="#333", corner_radius=6)
        ctrl_frame.pack(side="left", padx=10)
        
        ctk.CTkLabel(ctrl_frame, text="时长(分):").pack(side="left", padx=(10, 5))
        self.entry_duration = ctk.CTkEntry(ctrl_frame, width=50)
        self.entry_duration.insert(0, "0") 
        self.entry_duration.pack(side="left", padx=5)

        ctk.CTkLabel(ctrl_frame, text="模式:").pack(side="left", padx=(15, 5))
        self.mode_var = tk.StringVar(value="standard")
        ctk.CTkRadioButton(ctrl_frame, text="标准(长视频)", variable=self.mode_var, value="standard").pack(side="left", padx=5)
        ctk.CTkRadioButton(ctrl_frame, text="高密(30s切片)", variable=self.mode_var, value="density").pack(side="left", padx=5)

        # 智能去重开关
        self.var_dedup = ctk.BooleanVar(value=True)
        self.chk_dedup = ctk.CTkCheckBox(ctrl_frame, text="智能去重", variable=self.var_dedup, checkbox_width=20, checkbox_height=20)
        self.chk_dedup.pack(side="left", padx=(15, 10))

        self.btn_run_video = ctk.CTkButton(file_frame, text="🚀 生成 Excel 数据", command=self.start_video_thread, fg_color="#2E7D32", state="disabled", font=("微软雅黑", 13, "bold"))
        self.btn_run_video.pack(side="right", padx=20)
        
        # Result Area
        info_frame = ctk.CTkFrame(parent, height=25, fg_color="transparent")
        info_frame.pack(fill="x", padx=5)
        ctk.CTkLabel(info_frame, text="⬇️ 结果 (纯文本 Tab 分隔，可直接 Ctrl+A 复制到 Excel)", font=("Arial", 11), text_color="#888").pack(side="left")
        
        self.txt_video_out = ctk.CTkTextbox(parent, font=("Consolas", 12), undo=True)
        self.txt_video_out.pack(pady=(5, 10), fill="both", expand=True)
        self.txt_video_out.insert("0.0", "👋 准备就绪。\n提示：启用【智能去重】可过滤同一 UI 错误的重复报警。\nExcel 模式已开启：所有换行符将被转换为 ' | ' 以保证粘贴格式安全。")

    def _init_image_ui(self, parent):
        ctrl_frame = ctk.CTkFrame(parent)
        ctrl_frame.pack(pady=10, fill="x", padx=10)
        ctk.CTkButton(ctrl_frame, text="[1] 导入目标图", command=self.select_image_file).pack(side="left", padx=5)
        self.lbl_img_name = ctk.CTkLabel(ctrl_frame, text="未选择", text_color="gray", width=80)
        self.lbl_img_name.pack(side="left")
        self.check_compare = ctk.CTkSwitch(ctrl_frame, text="双语对比", command=self.toggle_compare_mode)
        self.check_compare.pack(side="left", padx=10)
        self.btn_ref_img = ctk.CTkButton(ctrl_frame, text="[2] 参考图(CN)", command=self.select_ref_image, state="disabled", fg_color="gray")
        self.btn_ref_img.pack(side="left", padx=5)
        self.btn_run_img = ctk.CTkButton(ctrl_frame, text="🚀 初次分析", command=self.start_image_init_thread, fg_color="#1565C0", state="disabled")
        self.btn_run_img.pack(side="right", padx=10)

        content_frame = ctk.CTkFrame(parent, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=10)
        self.preview_frame = ctk.CTkFrame(content_frame, width=280)
        self.preview_frame.pack(side="left", fill="y", padx=(0, 10))
        self.lbl_preview = ctk.CTkLabel(self.preview_frame, text="[图片预览]")
        self.lbl_preview.place(relx=0.5, rely=0.5, anchor="center")
        self.txt_img_out = ctk.CTkTextbox(content_frame, font=("微软雅黑", 12))
        self.txt_img_out.pack(side="right", fill="both", expand=True)

        chat_frame = ctk.CTkFrame(parent, height=50, fg_color="#2B2B2B")
        chat_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.entry_chat = ctk.CTkEntry(chat_frame, placeholder_text="Tell AI how to fix...", font=("微软雅黑", 12))
        self.entry_chat.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        self.entry_chat.bind("<Return>", lambda event: self.start_chat_thread())
        self.btn_chat = ctk.CTkButton(chat_frame, text="发送微调", command=self.start_chat_thread, fg_color="#00897B", width=120)
        self.btn_chat.pack(side="right", padx=10, pady=10)

    # ==============================================================================
    # 🧩 辅助功能
    # ==============================================================================
    
    def open_glossary(self):
        os.startfile(GLOSSARY_FILE) if os.name == 'nt' else os.system(f"open {GLOSSARY_FILE}")

    def toggle_compare_mode(self):
        if self.check_compare.get() == 1:
            self.btn_ref_img.configure(state="normal", fg_color="#1565C0")
        else:
            self.btn_ref_img.configure(state="disabled", fg_color="gray")
            self.ref_image_path = None

    def get_dynamic_prompt(self, base_prompt):
        target_lang = self.lang_combo.get()
        final_prompt = base_prompt.replace("{target_lang}", target_lang)
        glossary_text = ""
        if os.path.exists(GLOSSARY_FILE):
            try:
                with open(GLOSSARY_FILE, "r", encoding="utf-8") as f: glossary_text = f.read()
            except: pass
        rules = "\n".join([f"- {item['rule']}" for item in self.evolution_memory])
        if glossary_text: final_prompt += f"\n\n[📚 Glossary Terminology]\n{glossary_text}\n"
        if rules: final_prompt += f"\n\n[🔥🔥 User-Defined Rules]\n{rules}\n"
        return final_prompt
    
    def seconds_to_hms(self, seconds):
        m = seconds // 60
        s = seconds % 60
        return f"{m}:{s:02d}"

    def parse_last_timestamp(self, text):
        matches = re.findall(r"(\d+):(\d+)", text)
        if not matches: return 0
        last_m, last_s = matches[-1]
        return int(last_m) * 60 + int(last_s)

    def get_video_duration_minutes(self, path):
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened(): return 5
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            duration = frames / fps
            cap.release()
            return int(duration // 60) + 1 
        except Exception as e:
            print(f"Duration Error: {e}")
            return 5

    def is_duplicate(self, line):
        if not self.var_dedup.get(): return False
        if not line.strip() or "\t" not in line: return False
        
        parts = line.split("\t")
        if len(parts) < 4: return False
        
        if "Original" in parts[3] or "Better" in parts[4]: return False
        
        current_original = parts[3].strip().lower()
        current_type = parts[2].strip().lower()
        
        for record in self.dedup_records:
            if record['type'] != current_type: continue
            seq = difflib.SequenceMatcher(None, current_original, record['original'])
            if seq.ratio() > 0.85: 
                print(f"Skipping Duplicate: {parts[3][:20]}...")
                return True
                
        self.dedup_records.append({'type': current_type, 'original': current_original})
        return False

    def insert_filtered_text(self, text_chunk):
        lines = text_chunk.split('\n')
        filtered_lines = []
        
        for line in lines:
            clean_line = line.strip()
            if not clean_line or "[END_OF_VIDEO]" in clean_line: continue 
            if "---" in clean_line or "```" in clean_line: continue 
            
            if self.is_duplicate(clean_line): continue
                
            filtered_lines.append(clean_line)
        
        if filtered_lines:
            text_to_insert = "\n".join(filtered_lines) + "\n"
            self.txt_video_out.insert("end", text_to_insert)
            self.txt_video_out.see("end")
            return text_to_insert
        return ""

    # ==============================================================================
    # 🎥 视频业务逻辑
    # ==============================================================================
    def select_video_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if f:
            self.file_path = f
            self.lbl_video_name.configure(text=os.path.basename(f), text_color="white")
            self.btn_run_video.configure(state="normal")
            
            duration = self.get_video_duration_minutes(f)
            self.entry_duration.delete(0, "end")
            self.entry_duration.insert(0, str(duration))
            self.update_status(f"Loaded: {os.path.basename(f)} (~{duration} min)")

    def start_video_thread(self):
        threading.Thread(target=self.run_video_logic, daemon=True).start()

    def run_video_logic(self):
        key = self.api_key_var.get().strip()
        if not key or not self.file_path: return
        
        self._save_config()
        self.btn_run_video.configure(state="disabled")
        self.progressbar.start()
        self.txt_video_out.delete("0.0", "end")
        
        self.dedup_records = []
        
        mode = self.mode_var.get()
        try: total_minutes = int(self.entry_duration.get())
        except: total_minutes = 5
        
        full_report_text = ""
        
        try:
            genai.configure(api_key=key)
            self.update_status(f"Uploading Video...")
            
            video_file = genai.upload_file(path=self.file_path)
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            if video_file.state.name == "FAILED": raise ValueError("Video upload failed.")

            self.update_status(f"Analyzing in {mode.upper()} mode...")
            model = genai.GenerativeModel(self.model_combo.get())
            
            sys_prompt = self.get_dynamic_prompt(SYSTEM_PROMPT)
            history = [{"role": "user", "parts": [sys_prompt, video_file]}]
            chat = model.start_chat(history=history)
            
            if mode == "density":
                if total_minutes > 10: 
                    self.txt_video_out.insert("0.0", "⚠️ Info: High-density mode is best for clips < 10 mins.\n")
                    total_minutes = 10
                
                steps = total_minutes * 2
                for i in range(steps):
                    start_str = self.seconds_to_hms(i * 30)
                    end_str = self.seconds_to_hms((i + 1) * 30)
                    
                    header_instr = "Include the Header Row." if i == 0 else "DO NOT output the Header Row."
                    step_prompt = DENSITY_SEGMENT_PROMPT.format(start_time=start_str, end_time=end_str, header_instruction=header_instr)
                    
                    self.update_status(f"Scanning: {start_str} - {end_str}...")
                    response = chat.send_message(step_prompt)
                    
                    added_text = self.insert_filtered_text(response.text.strip())
                    full_report_text += added_text
                    time.sleep(2)
            else:
                self.update_status("Auditing (Initial Pass)...")
                response = chat.send_message(STANDARD_INIT_PROMPT)
                
                added_text = self.insert_filtered_text(response.text.strip())
                full_report_text += added_text
                
                total_seconds = total_minutes * 60
                last_ts_sec = self.parse_last_timestamp(response.text)
                
                retry_count = 0
                while last_ts_sec < (total_seconds - 30) and "[END_OF_VIDEO]" not in response.text and retry_count < 10:
                    retry_count += 1
                    last_ts_str = self.seconds_to_hms(last_ts_sec)
                    self.update_status(f"Continuing from {last_ts_str} (Pass {retry_count})...")
                    
                    response = chat.send_message(STANDARD_CONTINUE_PROMPT.format(last_timestamp=last_ts_str))
                    
                    added_text = self.insert_filtered_text(response.text.strip())
                    full_report_text += added_text
                    
                    new_last_ts = self.parse_last_timestamp(response.text)
                    if new_last_ts <= last_ts_sec: break
                    last_ts_sec = new_last_ts
                    time.sleep(2)

            self.add_new_history(full_report_text, f"[VID-{mode}] {os.path.basename(self.file_path)}")
            self.update_status("✅ DONE - Ready for Excel Copy")
            
            try: genai.delete_file(video_file.name)
            except: pass
            
        except Exception as e:
            self.update_status(f"Error: {str(e)}", True)
        finally:
            self.progressbar.stop()
            self.btn_run_video.configure(state="normal")

    # ==============================================================================
    # 🖼️ 图片业务逻辑
    # ==============================================================================
    def select_image_file(self):
        f = filedialog.askopenfilename(filetypes=[("Image", "*.jpg *.png *.jpeg *.webp")])
        if f:
            self.image_path = f
            self.lbl_img_name.configure(text=os.path.basename(f), text_color="white")
            self.btn_run_img.configure(state="normal")
            self.chat_session = None 
            try:
                img = Image.open(f)
                img.thumbnail((260, 260)) 
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.lbl_preview.configure(image=ctk_img, text="")
            except: pass

    def select_ref_image(self):
        f = filedialog.askopenfilename(filetypes=[("Image", "*.jpg *.png *.jpeg *.webp")])
        if f: self.ref_image_path = f

    def start_image_init_thread(self):
        threading.Thread(target=self.run_image_init, daemon=True).start()

    def run_image_init(self):
        key = self.api_key_var.get().strip()
        if not key or not self.image_path: return
        self._save_config()
        self.btn_run_img.configure(state="disabled")
        self.progressbar.start()

        try:
            genai.configure(api_key=key)
            self.update_status(f"Analyzing Image ({self.lang_combo.get()})...")
            
            content_list = [self.get_dynamic_prompt(IMAGE_PROMPT_INIT)]
            with open(self.image_path, "rb") as f:
                content_list.append({"mime_type": "image/jpeg", "data": f.read()})
            if self.check_compare.get() == 1 and self.ref_image_path:
                with open(self.ref_image_path, "rb") as f:
                    content_list.append({"mime_type": "image/jpeg", "data": f.read()})

            model = genai.GenerativeModel(self.model_combo.get())
            self.chat_session = model.start_chat(history=[])
            self.session_api_key = key 
            
            response = self.chat_session.send_message(content_list)
            
            self.txt_img_out.delete("0.0", "end")
            self.txt_img_out.insert("0.0", response.text)
            self.add_new_history(response.text, f"[IMG] {os.path.basename(self.image_path)}")
            self.update_status("Analysis Complete")

        except Exception as e:
            self.update_status(f"Error: {str(e)}", True)
        finally:
            self.progressbar.stop()
            self.btn_run_img.configure(state="normal")

    def start_chat_thread(self):
        user_input = self.entry_chat.get().strip()
        if not user_input: return
        
        current_ui_key = self.api_key_var.get().strip()
        if not self.chat_session or (self.session_api_key != current_ui_key):
            self.update_status("Reconnecting session...")
            self.chat_session = None 
            if not self.rebuild_session_from_history(): return 

        self.entry_chat.delete(0, 'end')
        threading.Thread(target=self.run_chat_followup, args=(user_input,), daemon=True).start()

    def rebuild_session_from_history(self):
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("Error", "API Key missing")
            return False
        current_content = self.txt_img_out.get("0.0", "end").strip()
        if not current_content: return False

        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(self.model_combo.get())
            history = [{"role": "user", "parts": ["Context:\n" + current_content]},
                       {"role": "model", "parts": ["Ready."]}]
            self.chat_session = model.start_chat(history=history)
            self.session_api_key = key
            self.update_status("Session Restored")
            return True
        except Exception as e:
            messagebox.showerror("Connection Error", f"Invalid Key: {str(e)}")
            return False

    def run_chat_followup(self, user_input):
        self.progressbar.start()
        self.update_status("Processing...")
        try:
            prompt = IMAGE_PROMPT_FOLLOWUP.format(user_input=user_input)
            response = self.chat_session.send_message(prompt)
            final_text = "\n\n" + "═" * 40 + "\n" + f"👤 User: {user_input}\n" + "─" * 40 + "\n" + f"🤖 AI:\n{response.text}"
            self.txt_img_out.insert("end", final_text)
            self.txt_img_out.see("end") 
            if hasattr(self, 'current_active_index'):
                 self.history_data[self.current_active_index]['content'] = self.txt_img_out.get("0.0", "end")
                 self._save_history_db()
            self.update_status("Done")
        except Exception as e:
            self.update_status(f"Error: {str(e)}", True)
        finally:
            self.progressbar.stop()

    # ==============================================================================
    # 💾 数据管理 (Fixed Syntax)
    # ==============================================================================
    def auto_learn_rule(self):
        key = self.api_key_var.get().strip()
        if not key: return
        complaint = simpledialog.askstring("Teach AI", "What did AI miss?")
        if not complaint: return
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-3-flash-preview")
            res = model.generate_content(REFLECTION_PROMPT.format(user_input=complaint))
            rule = res.text.strip()
            if messagebox.askyesno("Save Rule", f"{rule}\n\nAdd to memory?"):
                self.evolution_memory.append({"date": datetime.now().strftime("%Y-%m-%d"), "rule": rule})
                self._save_evolution_db()
                messagebox.showinfo("Success", "Rule added.")
        except Exception as e: messagebox.showerror("Error", str(e))

    def update_status(self, text, is_error=False):
        color = "#FF5252" if is_error else "#E0E0E0"
        try: self.lbl_status.configure(text=text, text_color=color)
        except: pass

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f: 
                json.dump({"api_key": self.api_key_var.get().strip(), "last_lang": self.lang_combo.get()}, f)
        except: pass

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f: 
                    data = json.load(f)
                    self.api_key_var.set(data.get("api_key", ""))
                    if "last_lang" in data: self.lang_combo.set(data["last_lang"])
            except: pass
            
    def _save_evolution_db(self):
        try:
            with open(EVOLUTION_DB_FILE, "w") as f: 
                json.dump(self.evolution_memory, f)
        except: pass

    def _load_evolution_db(self):
        if os.path.exists(EVOLUTION_DB_FILE):
            try:
                with open(EVOLUTION_DB_FILE, "r") as f: 
                    self.evolution_memory = json.load(f)
            except: pass
    
    def _load_history_db(self):
        if os.path.exists(HISTORY_DB_FILE):
            try:
                with open(HISTORY_DB_FILE, "r", encoding="utf-8") as f: 
                    self.history_data = json.load(f)
            except:
                try: 
                    with open(HISTORY_DB_FILE, "r", encoding="gbk") as f: 
                        self.history_data = json.load(f)
                except: self.history_data = []
            self._refresh_history_ui()
            
    def _save_history_db(self):
        try: 
            with open(HISTORY_DB_FILE, "w") as f: 
                json.dump(self.history_data, f)
        except: pass

    def add_new_history(self, content, title):
        self.history_data.append({"title": title, "date": datetime.now().strftime("%m-%d %H:%M"), "content": content})
        self._save_history_db()
        self._refresh_history_ui()

    def _refresh_history_ui(self):
        for w in self.history_list_frame.winfo_children(): w.destroy()
        for idx, item in enumerate(reversed(self.history_data)):
            real_idx = len(self.history_data) - 1 - idx
            ctk.CTkButton(self.history_list_frame, text=f"{item['title']}\n{item['date']}", 
                          fg_color="transparent", border_width=1, border_color="#444",
                          command=lambda i=real_idx: self.load_history(i)).pack(pady=2, fill="x")

    def load_history(self, idx):
        data = self.history_data[idx]
        target = self.txt_img_out if "[IMG]" in data['title'] else self.txt_video_out
        target.delete("0.0", "end")
        target.insert("0.0", data['content'])
        self.current_active_index = idx
        self.chat_session = None 
        self.session_api_key = None

    def delete_current_history(self):
        if hasattr(self, 'current_active_index'):
            del self.history_data[self.current_active_index]
            self._save_history_db()
            self._refresh_history_ui()
            self.txt_video_out.delete("0.0", "end")

if __name__ == "__main__":
    app = VideoLocalizationApp()
    app.mainloop()