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
# 🧠 PROMPT 区域 (已加入反幻觉指令)
# ==============================================================================

SYSTEM_PROMPT = """
[Role]
You are a Senior Localization Director (LQA). 
Target Language: **{target_lang}**.

[Format Rules]
1. Output PURE TEXT with Tab Delimiters (\\t) for Excel.
2. Columns: Time | Location (CN) | Issue Type (CN) | Original | Better {target_lang} | Analysis (CN)
3. **Location**: Use PURE Chinese (e.g., "主界面").
4. **Time**: m:ss format.
"""

# --- 模式 1：标准模式 Prompt ---
STANDARD_INIT_PROMPT = """
[Task]
Audit the video from **00:00** as far as you can.

[Content]
- Report capitalization, spacing, punctuation, and phrasing errors.
- **Header Row**: Include it at the very top.
"""

STANDARD_CONTINUE_PROMPT = """
[Task]
**Continue auditing exactly from {last_timestamp}**.
Do NOT repeat the Header Row.
Keep listing issues until the end of the video.
"""

# --- 模式 2：高密度模式 Prompt (动态时间版) ---
DENSITY_SEGMENT_PROMPT = """
[STRICT TIMEFRAME]
Audit ONLY from **{start_time}** to **{end_time}**.

[🚨 ANTI-HALLUCINATION PROTOCOL]
1. If the video ends before {end_time}, **STOP auditing immediately**.
2. Do NOT invent issues for non-existent footage (e.g., black screen).
3. If no errors are found in this chunk, output nothing.

[Instruction]
1. This is a High-Density Scan.
2. List EVERY single issue.
3. Location: PURE CHINESE.

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
2. 保持专业、客观、简练。
3. **Issue Type** 和 **Deep Analysis** 必须使用中文。

[格式模版]
【🕹️ 界面场景】...
【🔍 问题发现与优化 ({target_lang})】...
【🛠️ UX建议】...
"""

IMAGE_PROMPT_FOLLOWUP = """
[任务]
基于上下文和用户新指令修改报告。

[用户指令]
"{user_input}"

[绝对禁止]
❌ 禁止输出客套话。
❌ 禁止重复之前的分析，只输出**修改后**的内容或**完整的更新版报告**。

[输出]
直接开始输出修改后的内容。
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

        self.title("Gemini 3 LQA 精确制导版 (v21.0 Anti-Hallucination)")
        self.geometry("1450x950")

        self.file_path = None
        self.image_path = None     
        self.ref_image_path = None 
        
        self.chat_session = None 
        self.session_api_key = None 
        
        self.history_data = []
        self.evolution_memory = [] 
        # 优先使用 Flash 模型，避免配额限制
        self.model_list = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]

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
        
        self.tab_video = self.tab_view.add("视频审计 (双模式)")
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
        self.model_combo.set("gemini-2.5-flash") # 默认设为最稳的Flash
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
        ctk.CTkButton(file_frame, text="导入视频", command=self.select_video_file).pack(side="left")
        self.lbl_video_name = ctk.CTkLabel(file_frame, text="未选择", text_color="gray")
        self.lbl_video_name.pack(side="left", padx=15)
        
        # 模式选择区
        mode_frame = ctk.CTkFrame(file_frame, fg_color="#333")
        mode_frame.pack(side="left", padx=20)
        
        # 🔥 修改：支持精确时间输入
        ctk.CTkLabel(mode_frame, text="时长 (mm:ss):").pack(side="left", padx=5)
        self.entry_duration = ctk.CTkEntry(mode_frame, width=80)
        self.entry_duration.insert(0, "4:15") # 默认示例
        self.entry_duration.pack(side="left", padx=5)

        ctk.CTkLabel(mode_frame, text="模式:").pack(side="left", padx=5)
        self.mode_var = tk.StringVar(value="standard")
        
        self.rb_standard = ctk.CTkRadioButton(mode_frame, text="基础模式", variable=self.mode_var, value="standard")
        self.rb_standard.pack(side="left", padx=5)
        
        self.rb_density = ctk.CTkRadioButton(mode_frame, text="高密度模式", variable=self.mode_var, value="density")
        self.rb_density.pack(side="left", padx=5)

        self.btn_run_video = ctk.CTkButton(file_frame, text="开始审计", command=self.start_video_thread, fg_color="#2E7D32", state="disabled")
        self.btn_run_video.pack(side="right")
        
        self.txt_video_out = ctk.CTkTextbox(parent, font=("Consolas", 12))
        self.txt_video_out.pack(pady=10, fill="both", expand=True)
        self.txt_video_out.insert("0.0", "👋 准备就绪。\n⚠️ 关键提示：请务必在上方输入视频的【准确时长】(如 4:15)。\n这能防止 AI 扫描黑屏区域并产生幻觉。")

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
    
    def seconds_to_hms(self, seconds):
        m = seconds // 60
        s = seconds % 60
        return f"{m}:{s:02d}"

    # 🔥 新增：解析用户输入的时长 (支持 "5" 或 "4:15")
    def parse_total_seconds(self, input_str):
        try:
            input_str = input_str.strip().replace("：", ":")
            if ":" in input_str:
                parts = input_str.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            else:
                return int(input_str) * 60
        except:
            return 300 # 默认5分钟

    def parse_last_timestamp(self, text):
        matches = re.findall(r"(\d+):(\d+)", text)
        if not matches:
            return 0
        last_m, last_s = matches[-1]
        return int(last_m) * 60 + int(last_s)

    # --- 图片逻辑 (不变) ---
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

    # --- 视频逻辑 ---
    def select_video_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if f:
            self.file_path = f
            self.lbl_video_name.configure(text=os.path.basename(f), text_color="white")
            self.btn_run_video.configure(state="normal")

    def start_video_thread(self):
        threading.Thread(target=self.run_video_logic, daemon=True).start()

    def run_video_logic(self):
        key = self.api_key_var.get().strip()
        if not key or not self.file_path: return
        
        self._save_config()
        self.btn_run_video.configure(state="disabled")
        self.progressbar.start()
        self.txt_video_out.delete("0.0", "end")
        
        mode = self.mode_var.get()
        # 🔥 获取精确秒数
        total_seconds_limit = self.parse_total_seconds(self.entry_duration.get())
        
        try:
            genai.configure(api_key=key)
            self.update_status(f"上传视频中...")
            
            video_file = genai.upload_file(path=self.file_path)
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            if video_file.state.name == "FAILED": raise ValueError("视频上传失败")

            # 🔥 智能模型切换
            selected_model_name = self.model_combo.get()
            if mode == "density":
                selected_model_name = "gemini-2.5-flash"
                self.txt_video_out.insert("0.0", f"⚡ 安全模式：切换至 {selected_model_name} 以防止配额超限。\n\n")

            self.update_status(f"视频就绪 (限时 {self.seconds_to_hms(total_seconds_limit)})...")
            model = genai.GenerativeModel(selected_model_name)
            
            sys_prompt = self.get_dynamic_prompt(SYSTEM_PROMPT)
            history = [{"role": "user", "parts": [sys_prompt, video_file]}]
            chat = model.start_chat(history=history)
            
            full_report = ""

            # --- 分支 1: 高密度模式 (按精确时间切片) ---
            if mode == "density":
                current_time = 0
                step_idx = 0
                
                # 🔥 while 循环：基于真实秒数判断
                while current_time < total_seconds_limit:
                    step_idx += 1
                    end_time = min(current_time + 30, total_seconds_limit)
                    
                    start_str = self.seconds_to_hms(current_time)
                    end_str = self.seconds_to_hms(end_time)
                    
                    header_instr = "Include the Header Row." if step_idx == 1 else "DO NOT output the Header Row."
                    
                    step_prompt = DENSITY_SEGMENT_PROMPT.format(
                        start_time=start_str,
                        end_time=end_str,
                        header_instruction=header_instr
                    )
                    
                    self.update_status(f"扫描进度: {start_str} - {end_str}...")
                    
                    # 智能重试
                    max_retries = 2
                    success = False
                    for attempt in range(max_retries):
                        try:
                            response = chat.send_message(step_prompt, generation_config={"max_output_tokens": 8192, "temperature": 0.2})
                            chunk_text = response.text.strip()
                            if step_idx > 1: chunk_text = "\n" + chunk_text
                            full_report += chunk_text
                            self.txt_video_out.insert("end", chunk_text + "\n")
                            self.txt_video_out.see("end")
                            success = True
                            break
                        except Exception as e:
                            if "429" in str(e) or "quota" in str(e).lower():
                                self.update_status(f"冷却 60s 重试 ({attempt+1})...", True)
                                time.sleep(60)
                            else:
                                self.txt_video_out.insert("end", f"\n[Error at {start_str}: {str(e)}]\n")
                                break
                    
                    current_time += 30
                    if not success: time.sleep(5) 
                    time.sleep(6) # 安全间隔

            # --- 分支 2: 基础模式 ---
            else:
                self.update_status("正在进行审计...")
                try:
                    response = chat.send_message(STANDARD_INIT_PROMPT, generation_config={"max_output_tokens": 8192, "temperature": 0.2})
                    full_report += response.text.strip()
                    self.txt_video_out.insert("end", response.text.strip() + "\n")
                    
                    last_ts_sec = self.parse_last_timestamp(response.text)
                    retry_count = 0
                    
                    # 只要未达到设定的总秒数，就继续
                    while last_ts_sec < (total_seconds_limit - 15) and retry_count < 10:
                        retry_count += 1
                        last_ts_str = self.seconds_to_hms(last_ts_sec)
                        self.update_status(f"续写中 (从 {last_ts_str})...")
                        
                        follow_prompt = STANDARD_CONTINUE_PROMPT.format(last_timestamp=last_ts_str)
                        response = chat.send_message(follow_prompt, generation_config={"max_output_tokens": 8192, "temperature": 0.2})
                        chunk = response.text.strip()
                        full_report += "\n" + chunk
                        self.txt_video_out.insert("end", "\n" + chunk)
                        self.txt_video_out.see("end")
                        
                        new_last_ts = self.parse_last_timestamp(chunk)
                        if new_last_ts <= last_ts_sec: break
                        last_ts_sec = new_last_ts
                        time.sleep(2)
                except Exception as e:
                    self.update_status(f"基础模式错误: {str(e)}", True)

            # 结束
            self.add_new_history(full_report, f"[VID-{mode}] {os.path.basename(self.file_path)}")
            self.update_status("✅ 审计完成")
            try: genai.delete_file(video_file.name)
            except: pass
            
        except Exception as e:
            self.update_status(f"严重错误: {str(e)}", True)
        finally:
            self.progressbar.stop()
            self.btn_run_video.configure(state="normal")

    # --- 辅助功能 ---
    def auto_learn_rule(self):
        key = self.api_key_var.get().strip()
        if not key: return
        complaint = simpledialog.askstring("吐槽", "哪里做错了？")
        if not complaint: return
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.5-flash")
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

    # --- 存储 ---
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

if __name__ == "__main__":
    app = VideoLocalizationApp()
    app.mainloop()