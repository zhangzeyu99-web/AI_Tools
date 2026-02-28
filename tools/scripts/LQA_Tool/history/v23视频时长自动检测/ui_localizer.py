import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import google.generativeai as genai
import os
import time
import threading
import json
import re
import math
import difflib  # [新增] 文本相似度计算
import cv2      # [新增] 视频时长读取
from datetime import datetime
from PIL import Image

# --- 全局配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- 文件路径 ---
CONFIG_FILE = "config.json"
HISTORY_DB_FILE = "history_db.json"
EVOLUTION_DB_FILE = "evolution_memory.json"
GLOSSARY_FILE = "glossary.txt"

TARGET_LANGUAGES = ["English", "German", "French", "Turkish", "Spanish", "Portuguese", "Russian"]

# ==============================================================================
# 🧠 PROMPT 区域 (针对 Excel 优化)
# ==============================================================================

# 通用角色设定
SYSTEM_PROMPT = """
[Role]
You are a Senior Localization Director (LQA). 
Target Language: **{target_lang}**.

[Format Rules - CRITICAL]
1. Output **ONLY** a table valid for Excel copy-paste.
2. Use **TAB (\\t)** as the delimiter between columns.
3. **NO** Markdown tables (no pipes |), **NO** code blocks (```), **NO** introductory text.
4. Columns: Time\\tLocation\\tIssue Type (CN)\\tOriginal\\tBetter {target_lang}\\tAnalysis (CN)
"""

# --- 模式 1：标准模式 Prompt ---
STANDARD_INIT_PROMPT = """
[Task]
Audit the video from **00:00** as far as you can.

[Content]
- Report capitalization, spacing, punctuation, and phrasing errors.
- Include the Header Row at the very top.
- If you reach the end of the video, output "[END_OF_VIDEO]" at the last line.
"""

STANDARD_CONTINUE_PROMPT = """
[Task]
**Continue auditing exactly from {last_timestamp}**.
Do NOT repeat the Header Row.
If you reach the end of the video, output "[END_OF_VIDEO]" at the last line.
"""

# --- 模式 2：高密度模式 Prompt ---
DENSITY_SEGMENT_PROMPT = """
[STRICT TIMEFRAME]
Audit ONLY from **{start_time}** to **{end_time}**.

[Instruction]
1. List EVERY single issue.
2. If no errors in this chunk, output nothing.
3. Strict Tab-separated format.

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

        self.title("Gemini 3 LQA Studio (Excel专用版)")
        self.geometry("1450x950")

        self.file_path = None
        self.image_path = None     
        self.ref_image_path = None 
        
        self.chat_session = None 
        self.session_api_key = None 
        
        self.history_data = []
        self.evolution_memory = [] 
        self.model_list = ["gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-2.5-flash"]
        
        # [新增] 去重记录列表
        self.dedup_records = []

        self._ensure_glossary_exists()
        self._init_ui()
        self._load_config()
        self._load_history_db()
        self._load_evolution_db()

    def _ensure_glossary_exists(self):
        if not os.path.exists(GLOSSARY_FILE):
            with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
                f.write("# 术语表\n# 羁绊 = Traits\n")

    def _init_ui(self):
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(0, weight=1)

        # --- 左侧：侧边栏 ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self.sidebar_frame, text="历史记录", font=("微软雅黑", 20, "bold")).grid(row=0, column=0, padx=20, pady=(20, 10))
        self.history_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="记录列表")
        self.history_list_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        ctk.CTkButton(self.sidebar_frame, text="删除选中", command=self.delete_current_history, fg_color="#D32F2F").grid(row=3, column=0, padx=20, pady=20)

        # --- 右侧：主操作区 ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        self._init_top_bar()

        self.tab_view = ctk.CTkTabview(self.main_frame)
        self.tab_view.pack(pady=10, padx=20, fill="both", expand=True)
        
        self.tab_video = self.tab_view.add("视频审计 (Excel模式)")
        self.tab_image = self.tab_view.add("截图交互精修")

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
        
        # API Key
        ctk.CTkLabel(config_frame, text="API Key:").pack(side="left", padx=10)
        self.api_key_var = tk.StringVar()
        ctk.CTkEntry(config_frame, textvariable=self.api_key_var, show="*", width=200).pack(side="left", padx=5)
        
        # 模型选择
        self.model_combo = ctk.CTkComboBox(config_frame, values=self.model_list, width=180)
        self.model_combo.set("gemini-3-flash-preview")
        self.model_combo.pack(side="left", padx=10)

        # 目标语言选择
        ctk.CTkLabel(config_frame, text="目标语言:", text_color="#4DB6AC").pack(side="left", padx=(15, 5))
        self.lang_combo = ctk.CTkComboBox(config_frame, values=TARGET_LANGUAGES, width=140, state="readonly")
        self.lang_combo.set("English")
        self.lang_combo.pack(side="left", padx=5)

        right_frame = ctk.CTkFrame(top_container, fg_color="transparent")
        right_frame.pack(side="right")
        ctk.CTkButton(right_frame, text="术语表", command=self.open_glossary, width=80, fg_color="#5C6BC0").pack(side="left", padx=5)
        ctk.CTkButton(right_frame, text="吐槽进化", command=self.auto_learn_rule, width=80, fg_color="#FF9800", text_color="black").pack(side="right", padx=5)

    def _init_video_ui(self, parent):
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.pack(pady=10, fill="x")
        ctk.CTkButton(file_frame, text="📂 导入视频", command=self.select_video_file, width=120).pack(side="left")
        self.lbl_video_name = ctk.CTkLabel(file_frame, text="未选择", text_color="gray")
        self.lbl_video_name.pack(side="left", padx=15)
        
        # 模式选择区
        mode_frame = ctk.CTkFrame(file_frame, fg_color="#333")
        mode_frame.pack(side="left", padx=20)
        
        # [修改] 时长自动识别，但保留手动修改能力
        ctk.CTkLabel(mode_frame, text="时长(分):").pack(side="left", padx=5)
        self.entry_duration = ctk.CTkEntry(mode_frame, width=50)
        self.entry_duration.insert(0, "0") 
        self.entry_duration.pack(side="left", padx=5)

        ctk.CTkLabel(mode_frame, text="模式:").pack(side="left", padx=(15, 5))
        self.mode_var = tk.StringVar(value="standard")
        
        self.rb_standard = ctk.CTkRadioButton(mode_frame, text="基础模式", variable=self.mode_var, value="standard")
        self.rb_standard.pack(side="left", padx=5)
        self.rb_density = ctk.CTkRadioButton(mode_frame, text="高密模式(30s)", variable=self.mode_var, value="density")
        self.rb_density.pack(side="left", padx=5)

        # [新增] 智能去重开关
        self.var_dedup = ctk.BooleanVar(value=True)
        self.chk_dedup = ctk.CTkCheckBox(mode_frame, text="智能去重", variable=self.var_dedup, checkbox_width=20, checkbox_height=20)
        self.chk_dedup.pack(side="left", padx=(15, 10))

        self.btn_run_video = ctk.CTkButton(file_frame, text="🚀 开始生成 Excel 数据", command=self.start_video_thread, fg_color="#2E7D32", state="disabled")
        self.btn_run_video.pack(side="right", padx=20)
        
        # [修改] 增加复制按钮
        tools_frame = ctk.CTkFrame(parent, height=30, fg_color="transparent")
        tools_frame.pack(fill="x", padx=5)
        ctk.CTkLabel(tools_frame, text="⬇️ 结果 (可直接 Ctrl+A 复制到 Excel)", font=("Arial", 10), text_color="#888").pack(side="left")
        
        self.txt_video_out = ctk.CTkTextbox(parent, font=("Consolas", 12), undo=True)
        self.txt_video_out.pack(pady=(5, 10), fill="both", expand=True)
        self.txt_video_out.insert("0.0", "👋 等待导入视频...\n支持自动获取时长，输出结果将自动去重并格式化为 Tab 分隔符。")

    def _init_image_ui(self, parent):
        # 保持原有的图片 UI 代码
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
        self.txt_img_out.insert("0.0", "👋 交互模式：请确保上方【目标语言】选择正确。")

        chat_frame = ctk.CTkFrame(parent, height=50, fg_color="#2B2B2B")
        chat_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.entry_chat = ctk.CTkEntry(chat_frame, placeholder_text="在此输入修改需求...", font=("微软雅黑", 12))
        self.entry_chat.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        self.entry_chat.bind("<Return>", lambda event: self.start_chat_thread())

        self.btn_chat = ctk.CTkButton(chat_frame, text="发送微调", command=self.start_chat_thread, fg_color="#00897B", width=120)
        self.btn_chat.pack(side="right", padx=10, pady=10)

    # --- 逻辑控制 ---
    def toggle_compare_mode(self):
        if self.check_compare.get() == 1:
            self.btn_ref_img.configure(state="normal", fg_color="#1565C0")
        else:
            self.btn_ref_img.configure(state="disabled", fg_color="gray")
            self.ref_image_path = None

    def open_glossary(self):
        os.startfile(GLOSSARY_FILE) if os.name == 'nt' else os.system(f"open {GLOSSARY_FILE}")

    def get_dynamic_prompt(self, base_prompt):
        target_lang = self.lang_combo.get()
        final_prompt = base_prompt.replace("{target_lang}", target_lang)
        glossary_text = ""
        if os.path.exists(GLOSSARY_FILE):
            try:
                with open(GLOSSARY_FILE, "r", encoding="utf-8") as f: glossary_text = f.read()
            except: pass
        rules = "\n".join([f"- {item['rule']}" for item in self.evolution_memory])
        if glossary_text: final_prompt += f"\n\n[📚 术语表]\n{glossary_text}\n"
        if rules: final_prompt += f"\n\n[🔥🔥 用户进化规则]\n{rules}\n"
        return final_prompt
    
    # 辅助：时间格式转换
    def seconds_to_hms(self, seconds):
        m = seconds // 60
        s = seconds % 60
        return f"{m}:{s:02d}"

    def parse_last_timestamp(self, text):
        matches = re.findall(r"(\d+):(\d+)", text)
        if not matches: return 0
        last_m, last_s = matches[-1]
        return int(last_m) * 60 + int(last_s)

    # [新增] 自动获取时长
    def get_video_duration_minutes(self, path):
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened(): return 5
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            duration = frames / fps
            cap.release()
            return int(duration // 60) + 1 # 向上取整
        except Exception as e:
            print(f"Duration Error: {e}")
            return 5

    # [新增] 核心去重算法
    def is_duplicate(self, line):
        if not self.var_dedup.get(): return False
        if not line.strip() or "\t" not in line: return False
        
        # 解析关键字段 (假设第4列是原文，第3列是类型)
        parts = line.split("\t")
        if len(parts) < 4: return False
        
        # 如果是表头，不参与去重但放行
        if "Original" in parts[3] or "Better" in parts[4]: return False
        
        current_original = parts[3].strip().lower()
        current_type = parts[2].strip().lower()
        
        for record in self.dedup_records:
            # 类型不同，不算重复
            if record['type'] != current_type: continue
            
            # 文本相似度计算
            seq = difflib.SequenceMatcher(None, current_original, record['original'])
            if seq.ratio() > 0.85: # 相似度阈值
                print(f"Filtering duplicate: {parts[3][:20]}...")
                return True
                
        # 如果不是重复，加入记录
        self.dedup_records.append({'type': current_type, 'original': current_original})
        return False

    # [新增] 智能文本插入器
    def insert_filtered_text(self, text_chunk):
        lines = text_chunk.split('\n')
        filtered_lines = []
        
        for line in lines:
            # 过滤 Markdown
            clean_line = line.replace("|", "").strip()
            # 如果是空行或者 [END_OF_VIDEO] 标记，保留
            if not clean_line or "[END_OF_VIDEO]" in clean_line: 
                continue 
                
            # 去重判断
            if self.is_duplicate(clean_line):
                continue
                
            filtered_lines.append(clean_line)
        
        if filtered_lines:
            text_to_insert = "\n".join(filtered_lines) + "\n"
            self.txt_video_out.insert("end", text_to_insert)
            self.txt_video_out.see("end")
            # 存入完整的 history (包含去重后的)
            return text_to_insert
        return ""

    # --- 视频逻辑 ---
    def select_video_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if f:
            self.file_path = f
            self.lbl_video_name.configure(text=os.path.basename(f), text_color="white")
            self.btn_run_video.configure(state="normal")
            
            # [功能] 自动获取时长
            duration = self.get_video_duration_minutes(f)
            self.entry_duration.delete(0, "end")
            self.entry_duration.insert(0, str(duration))
            self.update_status(f"已加载: {os.path.basename(f)} (约 {duration} 分钟)")

    def start_video_thread(self):
        threading.Thread(target=self.run_video_logic, daemon=True).start()

    def run_video_logic(self):
        key = self.api_key_var.get().strip()
        if not key or not self.file_path: return
        
        self._save_config()
        self.btn_run_video.configure(state="disabled")
        self.progressbar.start()
        self.txt_video_out.delete("0.0", "end")
        
        # [初始化] 清空去重记录
        self.dedup_records = []
        
        mode = self.mode_var.get()
        try: total_minutes = int(self.entry_duration.get())
        except: total_minutes = 5
        
        full_report_text = ""
        
        try:
            genai.configure(api_key=key)
            self.update_status(f"上传视频中...")
            
            video_file = genai.upload_file(path=self.file_path)
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            if video_file.state.name == "FAILED": raise ValueError("视频上传失败")

            self.update_status(f"视频就绪，启动【{mode}】模式...")
            model = genai.GenerativeModel(self.model_combo.get())
            
            sys_prompt = self.get_dynamic_prompt(SYSTEM_PROMPT)
            history = [{"role": "user", "parts": [sys_prompt, video_file]}]
            chat = model.start_chat(history=history)
            
            # --- 分支 1: 高密度模式 (High-Density) ---
            if mode == "density":
                if total_minutes > 10: 
                    self.txt_video_out.insert("0.0", "⚠️ 警告：高密度模式建议用于10分钟以内视频。\n")
                    total_minutes = 10
                
                steps = total_minutes * 2
                for i in range(steps):
                    start_str = self.seconds_to_hms(i * 30)
                    end_str = self.seconds_to_hms((i + 1) * 30)
                    
                    header_instr = "Include the Header Row." if i == 0 else "DO NOT output the Header Row."
                    step_prompt = DENSITY_SEGMENT_PROMPT.format(start_time=start_str, end_time=end_str, header_instruction=header_instr)
                    
                    self.update_status(f"高密度扫描: {start_str} - {end_str}...")
                    response = chat.send_message(step_prompt)
                    
                    # [核心] 使用过滤函数插入
                    added_text = self.insert_filtered_text(response.text.strip())
                    full_report_text += added_text
                    
                    time.sleep(2)

            # --- 分支 2: 基础模式 (Standard) ---
            else:
                self.update_status("正在进行全时长审计...")
                response = chat.send_message(STANDARD_INIT_PROMPT)
                
                # [核心] 使用过滤函数插入
                added_text = self.insert_filtered_text(response.text.strip())
                full_report_text += added_text
                
                # 续写逻辑
                total_seconds = total_minutes * 60
                last_ts_sec = self.parse_last_timestamp(response.text)
                
                retry_count = 0
                while last_ts_sec < (total_seconds - 30) and "[END_OF_VIDEO]" not in response.text and retry_count < 8:
                    retry_count += 1
                    last_ts_str = self.seconds_to_hms(last_ts_sec)
                    self.update_status(f"续写中 (从 {last_ts_str} 开始)...")
                    
                    response = chat.send_message(STANDARD_CONTINUE_PROMPT.format(last_timestamp=last_ts_str))
                    
                    # [核心] 使用过滤函数插入
                    added_text = self.insert_filtered_text(response.text.strip())
                    full_report_text += added_text
                    
                    new_last_ts = self.parse_last_timestamp(response.text)
                    if new_last_ts <= last_ts_sec: break
                    last_ts_sec = new_last_ts
                    time.sleep(2)

            self.add_new_history(full_report_text, f"[VID-{mode}] {os.path.basename(self.file_path)}")
            self.update_status("✅ 审计完成 - 请直接全选文本框内容复制")
            
            try: genai.delete_file(video_file.name)
            except: pass
            
        except Exception as e:
            self.update_status(f"错误: {str(e)}", True)
        finally:
            self.progressbar.stop()
            self.btn_run_video.configure(state="normal")

    # --- 图片逻辑 & 其他辅助函数 (保持原样) ---
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
            self.update_status(f"正在分析 ({self.lang_combo.get()})...")
            
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
            self.update_status("分析完成")

        except Exception as e:
            self.update_status(f"错误: {str(e)}", True)
        finally:
            self.progressbar.stop()
            self.btn_run_img.configure(state="normal")

    def start_chat_thread(self):
        user_input = self.entry_chat.get().strip()
        if not user_input: return
        
        current_ui_key = self.api_key_var.get().strip()
        if not self.chat_session or (self.session_api_key != current_ui_key):
            self.update_status("配置变更，重建会话...")
            self.chat_session = None 
            if not self.rebuild_session_from_history(): return 

        self.entry_chat.delete(0, 'end')
        threading.Thread(target=self.run_chat_followup, args=(user_input,), daemon=True).start()

    def rebuild_session_from_history(self):
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("提示", "API Key 为空")
            return False
        current_content = self.txt_img_out.get("0.0", "end").strip()
        if not current_content: return False

        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(self.model_combo.get())
            history = [{"role": "user", "parts": ["这是上下文：\n" + current_content]},
                       {"role": "model", "parts": ["已同步，请继续。"]}]
            self.chat_session = model.start_chat(history=history)
            self.session_api_key = key
            self.update_status("会话重建成功")
            return True
        except Exception as e:
            messagebox.showerror("连接失败", f"无效 Key: {str(e)}")
            return False

    def run_chat_followup(self, user_input):
        self.progressbar.start()
        self.update_status("处理中...")
        try:
            prompt = IMAGE_PROMPT_FOLLOWUP.format(user_input=user_input)
            response = self.chat_session.send_message(prompt)
            final_text = "\n\n" + "═" * 40 + "\n" + f"👤 您说：{user_input}\n" + "─" * 40 + "\n" + f"🤖 AI 回复：\n{response.text}"
            self.txt_img_out.insert("end", final_text)
            self.txt_img_out.see("end") 
            if hasattr(self, 'current_active_index'):
                 self.history_data[self.current_active_index]['content'] = self.txt_img_out.get("0.0", "end")
                 self._save_history_db()
            self.update_status("完成")
        except Exception as e:
            self.update_status(f"交互错误: {str(e)}", True)
        finally:
            self.progressbar.stop()

    def auto_learn_rule(self):
        key = self.api_key_var.get().strip()
        if not key: return
        complaint = simpledialog.askstring("吐槽", "哪里做错了？")
        if not complaint: return
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-3-flash-preview")
            res = model.generate_content(REFLECTION_PROMPT.format(user_input=complaint))
            rule = res.text.strip()
            if messagebox.askyesno("规则提取", f"{rule}\n\n是否入库？"):
                self.evolution_memory.append({"date": datetime.now().strftime("%Y-%m-%d"), "rule": rule})
                self._save_evolution_db()
                messagebox.showinfo("成功", "规则已更新")
        except Exception as e: messagebox.showerror("错误", str(e))

    def update_status(self, text, is_error=False):
        color = "#FF5252" if is_error else "#E0E0E0"
        try: self.lbl_status.configure(text=text, text_color=color)
        except: pass

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f: 
                json.dump({
                    "api_key": self.api_key_var.get().strip(),
                    "last_lang": self.lang_combo.get()
                }, f)
        except: pass

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f: 
                    data = json.load(f)
                    self.api_key_var.set(data.get("api_key", ""))
                    if "last_lang" in data:
                        self.lang_combo.set(data["last_lang"])
            except: pass
            
    def _save_evolution_db(self):
        try:
            with open(EVOLUTION_DB_FILE, "w") as f: json.dump(self.evolution_memory, f)
        except: pass

    def _load_evolution_db(self):
        if os.path.exists(EVOLUTION_DB_FILE):
            try:
                with open(EVOLUTION_DB_FILE, "r") as f: self.evolution_memory = json.load(f)
            except: pass
    
    def _load_history_db(self):
        if os.path.exists(HISTORY_DB_FILE):
            try:
                with open(HISTORY_DB_FILE, "r", encoding="utf-8") as f: self.history_data = json.load(f)
            except:
                try: 
                    with open(HISTORY_DB_FILE, "r", encoding="gbk") as f: self.history_data = json.load(f)
                except: self.history_data = []
            self._refresh_history_ui()
            
    def _save_history_db(self):
        try:
            with open(HISTORY_DB_FILE, "w") as f: json.dump(self.history_data, f)
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