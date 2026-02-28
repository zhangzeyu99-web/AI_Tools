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
# 如果您还没修好Pillow，这个版本也不依赖Pillow，确保稳定

# --- 全局配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- 文件路径 ---
CONFIG_FILE = "config.json"
HISTORY_DB_FILE = "history_db.json"
EVOLUTION_DB_FILE = "evolution_memory.json"

# ==============================================================================
# 🧠 PROMPT 区域
# ==============================================================================

VIDEO_PROMPT = """
[Role]
You are a Senior Localization Director with 15 years of experience in Game/App QA.
Your working style is **Extremely Pedantic** and **Detail-Oriented**.

[Task]
Perform a frame-by-frame **Exhaustive Deep Audit** of the video content.
The video contains English UI/Text. Your goal is to identify ALL possible errors for **Chinese Developers**.

[Strategy]
1. **Be Picky**: Report slight capitalization inconsistencies, spacing errors, and punctuation marks.
2. **Lower Threshold**: Demand "native" English.
3. **Volume**: List every single instance found.

[Output Rules]
1. **Format**: Output PURE TEXT with **Tab Delimiters (\\t)**. NO Markdown tables.
2. **Columns**: Time \\t Location \\t ❌ Original Text \\t ⚠️ Issue Type \\t 🟢 Better English \\t 💡 Deep Analysis (Chinese)
"""

IMAGE_PROMPT = """
[Role]
You are a Top-tier Game Localization Expert (LQA) and UI/UX Planner.
Your task is to analyze UI text in a game screenshot, considering Context, Space Constraints, and Player UX.

[Output Format - JSON Only]
You MUST output valid JSON code strictly following this structure. Do not wrap in markdown code blocks.
{
  "ui_context": "Identified Screen Type",
  "audit_results": [
    {
      "original_text": "Extracted Text",
      "location": "Description",
      "issue_type": "Issue Category",
      "severity": "High/Medium/Low",
      "optimized_suggestion": "Suggested Text",
      "rationale": "Reason & UX consideration"
    }
  ],
  "global_suggestions": "Macro suggestions for layout/fonts"
}
"""

REFLECTION_PROMPT = """
[Task]
The user is complaining about a missed error. Analyze the user's feedback and extract a **General Rule**.
[User Feedback] "{user_input}"
[Output] Output ONLY the rule sentence in English.
"""

# ==============================================================================
# 🏗️ 主程序类
# ==============================================================================

class VideoLocalizationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gemini 3 综合审计终端 (Compat Edition)")
        self.geometry("1450x900")

        self.file_path = None
        self.image_path = None
        self.history_data = []
        self.evolution_memory = [] 
        
        self.model_list = ["gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-2.5-flash"]

        self._init_ui()
        self._load_config()
        self._load_history_db()
        self._load_evolution_db()

    def _init_ui(self):
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(0, weight=1)

        # --- 左侧：侧边栏 ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self.sidebar_frame, text="🕒 历史记录", font=("微软雅黑", 20, "bold")).grid(row=0, column=0, padx=20, pady=(20, 10))

        self.history_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="记录列表")
        self.history_list_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")

        ctk.CTkButton(self.sidebar_frame, text="🗑️ 删除记录", command=self.delete_current_history, fg_color="#D32F2F").grid(row=3, column=0, padx=20, pady=20)

        # --- 右侧：主操作区 ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        # 1. 顶部配置条
        self._init_top_bar()

        # 2. 功能切换区 (TabView)
        self.tab_view = ctk.CTkTabview(self.main_frame)
        self.tab_view.pack(pady=10, padx=20, fill="both", expand=True)
        
        self.tab_video = self.tab_view.add("🎥 视频流审计")
        self.tab_image = self.tab_view.add("🖼️ 截图 UI 精修")

        self._init_video_ui(self.tab_video)
        self._init_image_ui(self.tab_image)

        # 3. 底部状态条
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
        
        self.model_combo = ctk.CTkComboBox(config_frame, values=self.model_list, width=180)
        self.model_combo.set("gemini-3-flash-preview")
        self.model_combo.pack(side="left", padx=10)

        evo_frame = ctk.CTkFrame(top_container, fg_color="#1E2736")
        evo_frame.pack(side="right", fill="x")
        
        ctk.CTkLabel(evo_frame, text="🧬 进化库", text_color="#64B5F6").pack(side="left", padx=10)
        self.lbl_evo_count = ctk.CTkLabel(evo_frame, text="0 条", text_color="silver")
        self.lbl_evo_count.pack(side="left", padx=5)
        ctk.CTkButton(evo_frame, text="吐槽/调教", command=self.auto_learn_rule, width=100, fg_color="#FF9800", text_color="black").pack(side="right", padx=10, pady=5)

    def _init_video_ui(self, parent):
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.pack(pady=10, fill="x")
        
        ctk.CTkButton(file_frame, text="📂 导入视频", command=self.select_video_file).pack(side="left")
        self.lbl_video_name = ctk.CTkLabel(file_frame, text="未选择视频", text_color="gray")
        self.lbl_video_name.pack(side="left", padx=15)
        self.btn_run_video = ctk.CTkButton(file_frame, text="▶️ 开始视频审计", command=self.start_video_thread, fg_color="#2E7D32", state="disabled")
        self.btn_run_video.pack(side="right")

        self.txt_video_out = ctk.CTkTextbox(parent, font=("Consolas", 12))
        self.txt_video_out.pack(pady=10, fill="both", expand=True)
        self.txt_video_out.insert("0.0", "👋 视频审计模式：适合长时间录屏的批量检查。\n输出格式：Tab 分隔 (Excel 直贴)。")
        
        ctk.CTkButton(parent, text="📋 复制结果", command=lambda: self.copy_text(self.txt_video_out)).pack(pady=5)

    def _init_image_ui(self, parent):
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.pack(pady=10, fill="x")
        
        ctk.CTkButton(file_frame, text="🖼️ 导入截图", command=self.select_image_file).pack(side="left")
        self.lbl_img_name = ctk.CTkLabel(file_frame, text="未选择图片", text_color="gray")
        self.lbl_img_name.pack(side="left", padx=15)
        self.btn_run_img = ctk.CTkButton(file_frame, text="✨ 开始深度精修", command=self.start_image_thread, fg_color="#1565C0", state="disabled")
        self.btn_run_img.pack(side="right")

        content_frame = ctk.CTkFrame(parent, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)

        self.txt_img_out = ctk.CTkTextbox(content_frame, font=("Consolas", 12))
        self.txt_img_out.pack(side="right", fill="both", expand=True)
        self.txt_img_out.insert("0.0", "👋 截图精修模式：输出 JSON 格式建议。")

        ctk.CTkButton(parent, text="📋 复制 JSON", command=lambda: self.copy_text(self.txt_img_out)).pack(pady=5)

    def update_status(self, text, is_error=False):
        color = "#FF5252" if is_error else "#E0E0E0"
        try:
            self.lbl_status.configure(text=text, text_color=color)
        except: pass

    def copy_text(self, widget):
        pyperclip.copy(widget.get("0.0", "end"))
        self.update_status("📋 内容已复制！")

    def get_dynamic_prompt(self, base_prompt):
        if not self.evolution_memory: return base_prompt
        rules = "\n".join([f"- {item['rule']}" for item in self.evolution_memory])
        return base_prompt + f"\n\n[🔥🔥 CRITICAL USER RULES]\n{rules}\n"

    def select_video_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if f:
            self.file_path = f
            self.lbl_video_name.configure(text=os.path.basename(f), text_color="white")
            self.btn_run_video.configure(state="normal")

    def select_image_file(self):
        f = filedialog.askopenfilename(filetypes=[("Image", "*.jpg *.png *.jpeg *.webp")])
        if f:
            self.image_path = f
            self.lbl_img_name.configure(text=os.path.basename(f), text_color="white")
            self.btn_run_img.configure(state="normal")

    def start_video_thread(self):
        threading.Thread(target=self.run_video_logic, daemon=True).start()

    def start_image_thread(self):
        threading.Thread(target=self.run_image_logic, daemon=True).start()

    def run_video_logic(self):
        key = self.api_key_var.get().strip()
        if not key or not self.file_path: return
        self._save_config()
        self.btn_run_video.configure(state="disabled")
        self.progressbar.start()

        try:
            genai.configure(api_key=key)
            self.update_status("⬆️ 上传视频...")
            video_file = genai.upload_file(path=self.file_path)
            
            while video_file.state.name == "PROCESSING":
                time.sleep(2)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED": raise ValueError("视频失败")

            self.update_status("🎥 分析中...")
            model = genai.GenerativeModel(self.model_combo.get())
            response = model.generate_content([self.get_dynamic_prompt(VIDEO_PROMPT), video_file])
            
            self.txt_video_out.delete("0.0", "end")
            self.txt_video_out.insert("0.0", response.text)
            self.add_new_history(response.text, f"[VID] {os.path.basename(self.file_path)}")
            self.update_status("✅ 完成")
            try: genai.delete_file(video_file.name)
            except: pass

        except Exception as e:
            self.update_status(f"❌ 错误: {str(e)}", True)
        finally:
            self.progressbar.stop()
            self.btn_run_video.configure(state="normal")

    def run_image_logic(self):
        key = self.api_key_var.get().strip()
        if not key or not self.image_path: return
        self._save_config()
        self.btn_run_img.configure(state="disabled")
        self.progressbar.start()

        try:
            genai.configure(api_key=key)
            self.update_status("🖼️ 分析图片...")
            
            with open(self.image_path, "rb") as f:
                image_data = f.read()
            
            model = genai.GenerativeModel(self.model_combo.get(), generation_config={"response_mime_type": "application/json"})
            content_parts = [
                {"mime_type": "image/jpeg", "data": image_data},
                self.get_dynamic_prompt(IMAGE_PROMPT)
            ]
            
            response = model.generate_content(content_parts)
            try:
                formatted = json.dumps(json.loads(response.text), indent=2, ensure_ascii=False)
            except: formatted = response.text

            self.txt_img_out.delete("0.0", "end")
            self.txt_img_out.insert("0.0", formatted)
            self.add_new_history(formatted, f"[IMG] {os.path.basename(self.image_path)}")
            self.update_status("✅ 完成")

        except Exception as e:
            self.update_status(f"❌ 错误: {str(e)}", True)
        finally:
            self.progressbar.stop()
            self.btn_run_img.configure(state="normal")

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
            
            if messagebox.askyesno("提取规则", f"{rule}\n\n存入？"):
                self.evolution_memory.append({"date": datetime.now().strftime("%Y-%m-%d"), "rule": rule})
                self._save_evolution_db()
                messagebox.showinfo("成功", "✅ 规则已更新")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # --- 修复后的文件保存函数 (兼容老版本Python) ---
    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"api_key": self.api_key_var.get().strip()}, f)
        except: pass
    
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.api_key_var.set(json.load(f).get("api_key", ""))
            except: pass

    def _load_evolution_db(self):
        if os.path.exists(EVOLUTION_DB_FILE):
            try:
                with open(EVOLUTION_DB_FILE, "r") as f:
                    self.evolution_memory = json.load(f)
            except: pass
        self.lbl_evo_count.configure(text=f"{len(self.evolution_memory)} 条")

    def _save_evolution_db(self):
        try:
            with open(EVOLUTION_DB_FILE, "w") as f:
                json.dump(self.evolution_memory, f)
        except: pass
        self.lbl_evo_count.configure(text=f"{len(self.evolution_memory)} 条")

    def _load_history_db(self):
        if os.path.exists(HISTORY_DB_FILE):
            try:
                # 尝试用 utf-8 读取 (标准格式)
                with open(HISTORY_DB_FILE, "r", encoding="utf-8") as f:
                    self.history_data = json.load(f)
            except UnicodeDecodeError:
                try:
                    # 如果失败，尝试用 gbk 读取 (Windows常见)
                    with open(HISTORY_DB_FILE, "r", encoding="gbk") as f:
                        self.history_data = json.load(f)
                except:
                    # 如果还不行，就初始化为空列表，防止报错
                    self.history_data = []
            except json.JSONDecodeError:
                # 如果文件内容坏了，初始化为空
                self.history_data = []
            
            # 无论如何，尝试刷新界面
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

    def delete_current_history(self):
        if hasattr(self, 'current_active_index'):
            del self.history_data[self.current_active_index]
            self._save_history_db()
            self._refresh_history_ui()

if __name__ == "__main__":
    app = VideoLocalizationApp()
    app.mainloop()