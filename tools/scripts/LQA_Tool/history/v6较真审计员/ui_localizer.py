import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import google.generativeai as genai
import os
import time
import threading
import pyperclip
import json
from datetime import datetime

# --- 全局配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- 文件路径 ---
CONFIG_FILE = "config.json"
HISTORY_DB_FILE = "history_db.json"
EVOLUTION_DB_FILE = "evolution_memory.json"

# --- 🧠 1. 核心审计 Prompt (高敏感度 + 穷尽模式) ---
BASE_PROMPT = """
[Role]
You are a Senior Localization Director with 15 years of experience in Game/App QA.
Your working style is **Extremely Pedantic** and **Detail-Oriented**.

[Task]
Perform a frame-by-frame **Exhaustive Deep Audit** of the video content.
The video contains English UI/Text. Your goal is to identify ALL possible errors for **Chinese Developers**.

[Strategy: Quantity AND Quality]
1. **Be Picky**: Do not overlook minor issues. Report EVERYTHING including slight capitalization inconsistencies, spacing errors, and punctuation marks.
2. **Lower Threshold**: If a phrase is even *slightly* unnatural, flag it. Do not ignore "passable" English; demand "native" English.
3. **Volume**: I expect a long list. Do not summarize. List every single instance found.

[Critical Audit Dimensions]
1. **Spelling**: Hunt down typos like "Login Sucess".
2. **Chinglish**: Identify unnatural phrasing (e.g., "Open the function" vs "Enable").
3. **Tone/Register**: Ensure professional consistency (Formal vs Casual).
4. **UI Layout**: Check for text truncation, overlapping, or alignment issues.
5. **Redundancy**: Simplify verbose text.
6. **Formatting**: Check spacing, capitalization, and punctuation.

[Output Rules - STRICTLY ENFORCED]
1. **Target Language**: Analyze in English logic, but write the **"Deep Analysis" (深度解析) column in CHINESE**.
2. **Format**: Output PURE TEXT with **Tab Delimiters (\\t)**. NO Markdown tables.

[Column Headers (Tab-Separated)]
Time	Location	❌ Original Text	⚠️ Issue Type	🟢 Better English	💡 Deep Analysis (Write in Chinese)
"""

# --- 🧠 2. 自我反思 Prompt (用于提取规则) ---
REFLECTION_PROMPT = """
[Task]
The user is complaining about a missed error or a wrong judgment in your previous audit.
Analyze the user's feedback and extract a **General, Actionable Audit Rule** to improve future performance.

[User Feedback]
"{user_input}"

[Requirement]
1. **Ignore Emotions**: Ignore angry or casual language (e.g., "Are you blind?"). Focus on the logic.
2. **Extract Rule**: Convert the specific complaint into a general rule (e.g., Complaint: "You missed the typo in 'Cancle'", Rule: "Strictly check spelling for common UI buttons like 'Cancel', 'Confirm'.").
3. **Language**: Output the rule in **English**.
4. **Format**: Output ONLY the rule sentence. No other text.
"""

class VideoLocalizationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gemini 3 自进化审计终端 (Self-Evolving)")
        self.geometry("1400x950")

        self.file_path = None
        self.processing = False
        self.history_data = []
        self.evolution_memory = [] 
        
        # --- 模型选择 ---
        self.model_list = [
            "gemini-3-flash-preview",  # ⚡ 速度快，适合反思和视频分析
            "gemini-3-pro-preview",    
            "gemini-2.5-flash",
        ]

        self._init_ui()
        self._load_config()
        self._load_history_db()
        self._load_evolution_db()

    def _init_ui(self):
        # === 整体布局 ===
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(0, weight=1)

        # --- 左侧：历史记录 ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="🕒 历史记录", font=("微软雅黑", 20, "bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.history_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="记录列表")
        self.history_list_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")

        self.btn_delete_history = ctk.CTkButton(self.sidebar_frame, text="🗑️ 删除记录", command=self.delete_current_history, fg_color="#D32F2F")
        self.btn_delete_history.grid(row=3, column=0, padx=20, pady=20)

        # --- 右侧：主操作区 ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        # 1. 顶部配置
        self.config_frame = ctk.CTkFrame(self.main_frame)
        self.config_frame.pack(pady=10, padx=20, fill="x")

        self.api_label = ctk.CTkLabel(self.config_frame, text="API Key:")
        self.api_label.pack(side="left", padx=(10, 5))
        self.api_key_var = tk.StringVar()
        self.api_entry = ctk.CTkEntry(self.config_frame, textvariable=self.api_key_var, show="*", width=300)
        self.api_entry.pack(side="left", padx=5)
        
        self.model_combo = ctk.CTkComboBox(self.config_frame, values=self.model_list, width=220)
        self.model_combo.set("gemini-3-flash-preview") 
        self.model_combo.pack(side="left", padx=20)

        # 2. 🧬 进化中心 (核心升级区)
        self.evo_frame = ctk.CTkFrame(self.main_frame, fg_color="#1E2736")
        self.evo_frame.pack(pady=5, padx=20, fill="x")
        
        self.lbl_evo = ctk.CTkLabel(self.evo_frame, text="🧬 进化记忆库", font=("微软雅黑", 12, "bold"), text_color="#64B5F6")
        self.lbl_evo.pack(side="left", padx=15, pady=8)
        
        self.lbl_evo_count = ctk.CTkLabel(self.evo_frame, text="规则数: 0", text_color="silver")
        self.lbl_evo_count.pack(side="left", padx=5)

        # 两个按钮：手动添加 vs 自动调教
        self.btn_manual_add = ctk.CTkButton(self.evo_frame, text="➕ 手动规则", command=self.add_manual_rule, width=100, fg_color="#455A64")
        self.btn_manual_add.pack(side="right", padx=(5, 15), pady=8)

        self.btn_auto_learn = ctk.CTkButton(self.evo_frame, text="🗣️ 结果不对？点此吐槽", command=self.auto_learn_rule, width=160, fg_color="#FF9800", text_color="black", hover_color="#F57C00")
        self.btn_auto_learn.pack(side="right", padx=5, pady=8)

        # 3. 文件操作
        self.file_frame = ctk.CTkFrame(self.main_frame)
        self.file_frame.pack(pady=10, padx=20, fill="x")
        self.btn_select = ctk.CTkButton(self.file_frame, text="📂 导入视频", command=self.select_file)
        self.btn_select.pack(side="left", padx=10, pady=10)
        self.lbl_filename = ctk.CTkLabel(self.file_frame, text="未选择文件", text_color="gray")
        self.lbl_filename.pack(side="left", padx=10)
        self.btn_run = ctk.CTkButton(self.file_frame, text="🔍 开始全面审计", command=self.start_analysis_thread, fg_color="#2E7D32", state="disabled", font=("微软雅黑", 14, "bold"), width=200)
        self.btn_run.pack(side="right", padx=10)

        # 4. 状态 & 内容
        self.progressbar = ctk.CTkProgressBar(self.main_frame, mode="indeterminate", width=800)
        self.progressbar.pack(pady=5, padx=20, fill="x")
        self.lbl_status = ctk.CTkLabel(self.main_frame, text="准备就绪", text_color="silver")
        self.lbl_status.pack()

        self.current_display_label = ctk.CTkLabel(self.main_frame, text="当前显示: [新任务]", font=("微软雅黑", 14, "bold"), text_color="#4FC3F7")
        self.current_display_label.pack(pady=(10, 0), anchor="w", padx=20)

        self.textbox = ctk.CTkTextbox(self.main_frame, font=("Consolas", 12), activate_scrollbars=True)
        self.textbox.pack(pady=10, padx=20, fill="both", expand=True)
        self.textbox.insert("0.0", "👋 欢迎使用自进化审计终端。\n\n🗣️【如何让 AI 变聪明】：\n点击右上角橙色的“结果不对？点此吐槽”按钮，用大白话告诉它哪里错了。\nAI 会自动反思并生成新规则，下次就不会犯同样的错了。\n\n⚡【审计模式】：高敏感度 + 穷尽列表。")

        self.btn_copy = ctk.CTkButton(self.main_frame, text="📋 复制 (Tab格式)", command=self.copy_to_clipboard)
        self.btn_copy.pack(pady=10)

    # --- 🧠 进化核心逻辑 (自动 & 手动) ---
    def _load_evolution_db(self):
        if os.path.exists(EVOLUTION_DB_FILE):
            try:
                with open(EVOLUTION_DB_FILE, "r", encoding="utf-8") as f:
                    self.evolution_memory = json.load(f)
            except: self.evolution_memory = []
        self.update_evo_ui()

    def _save_evolution_db(self):
        try:
            with open(EVOLUTION_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self.evolution_memory, f, ensure_ascii=False, indent=2)
        except: pass
        self.update_evo_ui()

    def update_evo_ui(self):
        count = len(self.evolution_memory)
        self.lbl_evo_count.configure(text=f"已积累规则: {count} 条")

    def add_manual_rule(self):
        rule = simpledialog.askstring("手动输入", "请输入新规则 (中文/English):")
        if rule:
            self._commit_rule(rule)

    def auto_learn_rule(self):
        """AI 自我反思逻辑"""
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("错误", "请先输入 API Key")
            return

        # 1. 获取用户吐槽
        complaint = simpledialog.askstring("AI 自我进化", "请指出刚才 AI 犯的错 (支持口语):\n例如：'那个 Login 拼错了你都没查出来！'")
        if not complaint: return

        self.update_status("🧠 AI 正在反思并提取规则...", is_error=False)
        
        # 2. 后台调用 AI 提取规则
        # 为了简单起见，这里直接在主线程调用（Gemini Flash 很快），避免复杂线程问题
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3-flash-preview")
            
            final_prompt = REFLECTION_PROMPT.format(user_input=complaint)
            response = model.generate_content(final_prompt)
            ai_extracted_rule = response.text.strip()

            # 3. 确认并入库
            confirm_msg = f"🔍 用户反馈: {complaint}\n\n🤖 AI 领悟到的新规则:\n{ai_extracted_rule}\n\n是否将此规则永久植入记忆库？"
            if messagebox.askyesno("进化确认", confirm_msg):
                self._commit_rule(ai_extracted_rule)
                messagebox.showinfo("成功", "✅ AI 已完成一次进化！下次生效。")
            else:
                self.update_status("❌ 已取消进化")

        except Exception as e:
            messagebox.showerror("反思失败", str(e))
            self.update_status("反思失败", is_error=True)

    def _commit_rule(self, rule_text):
        timestamp = datetime.now().strftime("%Y-%m-%d")
        self.evolution_memory.append({"date": timestamp, "rule": rule_text})
        self._save_evolution_db()
        self.update_status("✅ 规则已更新")

    def construct_dynamic_prompt(self):
        # 英文指令 + 用户积累的进化规则
        if not self.evolution_memory:
            memory_text = ""
        else:
            rules_str = "\n".join([f"- {item['rule']}" for item in self.evolution_memory])
            # 强化语气，防止 AI 因为进化规则而遗漏基础检查
            memory_text = f"\n[🔥🔥 CRITICAL USER RULES - DO NOT IGNORE]\nPay SPECIAL attention to these user-defined constraints:\n{rules_str}\n"
        return BASE_PROMPT + memory_text

    # --- 基础功能 (保持不变) ---
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.api_key_var.set(config.get("api_key", ""))
            except: pass

    def _save_config(self):
        current_key = self.api_key_var.get().strip()
        if current_key:
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump({"api_key": current_key}, f)
            except: pass

    def _load_history_db(self):
        if os.path.exists(HISTORY_DB_FILE):
            try:
                with open(HISTORY_DB_FILE, "r", encoding="utf-8") as f:
                    self.history_data = json.load(f)
                    self._refresh_history_list()
            except: pass

    def _save_history_db(self):
        try:
            with open(HISTORY_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except: pass

    def _refresh_history_list(self):
        for widget in self.history_list_frame.winfo_children():
            widget.destroy()
        for index, item in enumerate(reversed(self.history_data)):
            real_index = len(self.history_data) - 1 - index
            btn = ctk.CTkButton(
                self.history_list_frame, 
                text=f"{item['title']}\n{item['date']}", 
                fg_color="transparent", 
                border_width=1, 
                border_color="#444", 
                anchor="w",
                command=lambda idx=real_index: self.load_history_content(idx)
            )
            btn.pack(pady=2, padx=5, fill="x")
            btn.bind("<Double-Button-1>", lambda event, idx=real_index: self.rename_history(idx))

    def add_new_history(self, content, video_name):
        timestamp = datetime.now().strftime("%m-%d %H:%M")
        self.history_data.append({"title": video_name, "date": timestamp, "content": content})
        self._save_history_db()
        self._refresh_history_list()
        self.load_history_content(len(self.history_data) - 1)

    def load_history_content(self, index):
        if 0 <= index < len(self.history_data):
            entry = self.history_data[index]
            self.textbox.delete("0.0", "end")
            self.textbox.insert("0.0", entry["content"])
            self.current_display_label.configure(text=f"当前显示: {entry['title']}")
            self.current_active_index = index

    def rename_history(self, index):
        new_title = simpledialog.askstring("重命名", "新标题:", initialvalue=self.history_data[index]["title"])
        if new_title:
            self.history_data[index]["title"] = new_title
            self._save_history_db()
            self._refresh_history_list()
            if hasattr(self, 'current_active_index') and self.current_active_index == index:
                self.current_display_label.configure(text=f"当前显示: {new_title}")

    def delete_current_history(self):
        if hasattr(self, 'current_active_index'):
            if messagebox.askyesno("确认", "删除此记录？"):
                del self.history_data[self.current_active_index]
                self._save_history_db()
                self._refresh_history_list()
                self.textbox.delete("0.0", "end")
                self.current_display_label.configure(text="当前显示: [无]")
                del self.current_active_index

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mov *.avi *.webm *.mkv")])
        if file_path:
            self.file_path = file_path
            self.lbl_filename.configure(text=os.path.basename(file_path), text_color="white")
            self.btn_run.configure(state="normal")
            self.update_status(f"已加载: {os.path.basename(file_path)}")

    def update_status(self, text, is_error=False):
        color = "#FF5252" if is_error else "#E0E0E0"
        self.lbl_status.configure(text=text, text_color=color)

    def start_analysis_thread(self):
        api_key = self.api_key_var.get().strip()
        if not api_key or not self.file_path: return
        self._save_config()
        self.processing = True
        self.btn_run.configure(state="disabled", text="Audit in Progress...")
        self.textbox.delete("0.0", "end")
        self.progressbar.start()
        threading.Thread(target=self.run_logic, args=(api_key, self.file_path, self.model_combo.get()), daemon=True).start()

    def run_logic(self, api_key, file_path, model_name):
        try:
            genai.configure(api_key=api_key)
            self.update_status("⬆️ Uploading Video...")
            video_file = genai.upload_file(path=file_path)
            
            self.update_status("⏳ Processing...")
            start_time = time.time()
            while video_file.state.name == "PROCESSING":
                if time.time() - start_time > 600: raise TimeoutError("Timeout")
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED": raise ValueError("Video Processing Failed")

            self.update_status(f"🧠 AI Analyzing [{model_name}]...")
            final_prompt = self.construct_dynamic_prompt()
            
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([final_prompt, video_file])
            
            self.after(0, lambda: self.add_new_history(response.text, os.path.basename(file_path)))
            self.update_status("✅ Complete!")
        except Exception as e:
            self.update_status(f"❌ Error: {str(e)}", is_error=True)
            self.textbox.insert("0.0", str(e))
        finally:
            if 'video_file' in locals(): 
                try: genai.delete_file(video_file.name)
                except: pass
            self.processing = False
            self.progressbar.stop()
            self.btn_run.configure(state="normal", text="🔍 开始全面审计")

    def copy_to_clipboard(self):
        pyperclip.copy(self.textbox.get("0.0", "end"))
        self.update_status("📋 Copied!")

if __name__ == "__main__":
    app = VideoLocalizationApp()
    app.mainloop()