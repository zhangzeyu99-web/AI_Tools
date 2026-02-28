import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import os
import threading
import time
import traceback

# === 依赖库导入 ===
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from google import genai
except ImportError as e:
    messagebox.showerror("缺少依赖", f"请先运行 pip install --upgrade google-genai selenium\n错误详情: {e}")
    exit()

SETTINGS_FILE = "settings.json"
TARGET_URL = "http://i.4399om.com/todo/list" 
GEMINI_MODEL_NAME = "gemini-2.5-flash"

class TodoApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"自动日报助手 (强制点击保存版)")
        self.root.geometry("900x850")

        # =================【UI 配置】=================
        default_font = ("Microsoft YaHei", 10)
        style = ttk.Style()
        style.configure(".", font=default_font)
        style.configure("TButton", font=default_font, padding=5)
        self.text_font = ("Microsoft YaHei", 10)

        # ================= 左侧：设置区 =================
        left_panel = ttk.Frame(root)
        left_panel.pack(side="left", fill="y", padx=15, pady=15)

        # 1. 账号设置
        frame_auth = ttk.LabelFrame(left_panel, text="1. 账号设置")
        frame_auth.pack(fill="x", pady=8)
        
        ttk.Label(frame_auth, text="OA账号:").pack(anchor="w", padx=10, pady=(5,0))
        self.entry_user = ttk.Entry(frame_auth, width=32, font=default_font)
        self.entry_user.pack(padx=10, pady=2)
        
        ttk.Label(frame_auth, text="OA密码:").pack(anchor="w", padx=10, pady=(5,0))
        self.entry_pwd = ttk.Entry(frame_auth, show="*", width=32, font=default_font)
        self.entry_pwd.pack(padx=10, pady=2)

        ttk.Label(frame_auth, text="Gemini Key:").pack(anchor="w", padx=10, pady=(5,0))
        self.entry_key = ttk.Entry(frame_auth, width=32, font=default_font)
        self.entry_key.pack(padx=10, pady=(2,10))

        # 2. 关键词
        frame_kw = ttk.LabelFrame(left_panel, text="2. 工作关键词")
        frame_kw.pack(fill="x", pady=8)
        self.text_keywords = tk.Text(frame_kw, height=6, width=32, font=self.text_font)
        self.text_keywords.pack(padx=10, pady=10)

        # 3. 填写范围控制
        frame_chk = ttk.LabelFrame(left_panel, text="3. 填写范围")
        frame_chk.pack(fill="x", pady=8)
        
        self.var_top5 = tk.BooleanVar(value=True)
        self.var_summary = tk.BooleanVar(value=True)
        self.var_todo = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(frame_chk, text="填写 [Top5重要事项]", variable=self.var_top5).pack(anchor="w", padx=10, pady=2)
        ttk.Checkbutton(frame_chk, text="填写 [本周总结]", variable=self.var_summary).pack(anchor="w", padx=10, pady=2)
        ttk.Checkbutton(frame_chk, text="填写 [Todo列表]", variable=self.var_todo).pack(anchor="w", padx=10, pady=(2,10))

        # 4. 操作按钮
        frame_btn = ttk.Frame(left_panel)
        frame_btn.pack(fill="x", pady=15)
        
        ttk.Button(frame_btn, text="🤖 第一步：AI 生成预览", command=self.generate_preview_thread).pack(fill="x", pady=5)
        ttk.Separator(frame_btn, orient="horizontal").pack(fill="x", pady=12)
        
        self.btn_run = ttk.Button(frame_btn, text="🚀 第二步：启动填写", command=self.start_automation_thread, state="disabled")
        self.btn_run.pack(fill="x", pady=5)
        
        ttk.Button(frame_btn, text="💾 保存配置", command=self.save_settings).pack(fill="x", pady=5)

        # ================= 右侧：预览与日志 =================
        right_panel = ttk.Frame(root)
        right_panel.pack(side="right", fill="both", expand=True, padx=15, pady=15)

        lbl_pre = ttk.Label(right_panel, text="【内容预览区】 (请先生成，确认无误后再启动)")
        lbl_pre.pack(anchor="w", pady=(0, 5))
        
        # Top 5 预览
        self.frame_p1 = ttk.LabelFrame(right_panel, text="Top 5 内容预览")
        self.frame_p1.pack(fill="x", pady=5)
        self.text_top5 = tk.Text(self.frame_p1, height=4, font=self.text_font)
        self.text_top5.pack(fill="both", padx=5, pady=5)

        # 总结 预览
        self.frame_p2 = ttk.LabelFrame(right_panel, text="总结 内容预览")
        self.frame_p2.pack(fill="x", pady=5)
        self.text_summary = tk.Text(self.frame_p2, height=4, font=self.text_font)
        self.text_summary.pack(fill="both", padx=5, pady=5)

        # Todo 预览
        self.frame_p3 = ttk.LabelFrame(right_panel, text="Todo 列表预览 (一行一条)")
        self.frame_p3.pack(fill="both", expand=True, pady=5)
        self.text_todo = tk.Text(self.frame_p3, height=8, font=self.text_font)
        self.text_todo.pack(fill="both", padx=5, pady=5)

        # 日志区
        frame_log = ttk.LabelFrame(right_panel, text="运行日志")
        frame_log.pack(fill="x", side="bottom", pady=(10, 0))
        self.log_area = scrolledtext.ScrolledText(frame_log, height=8, state='disabled', font=("Consolas", 9))
        self.log_area.pack(fill="both", padx=5, pady=5)

        self.load_settings()

    def log(self, msg):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {msg}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def save_settings(self):
        settings = {
            "username": self.entry_user.get(),
            "password": self.entry_pwd.get(),
            "api_key": self.entry_key.get().strip(),
            "keywords": self.text_keywords.get("1.0", tk.END).strip()
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        self.log("配置已保存。")

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.entry_user.insert(0, data.get("username", ""))
                    self.entry_pwd.insert(0, data.get("password", ""))
                    self.entry_key.insert(0, data.get("api_key", ""))
                    self.text_keywords.insert("1.0", data.get("keywords", ""))
            except: pass

    # ================= AI 生成 =================
    def generate_preview_thread(self):
        threading.Thread(target=self._generate_preview, daemon=True).start()

    def _generate_preview(self):
        self.save_settings()
        api_key = self.entry_key.get().strip()
        keywords = [x.strip() for x in self.text_keywords.get("1.0", tk.END).strip().split('\n') if x.strip()]
        
        if not api_key:
            messagebox.showerror("错误", "请先填写 Gemini Key")
            return
            
        self.log(f"⚡ 正在请求 AI 生成 ({GEMINI_MODEL_NAME})...")
        
        try:
            client = genai.Client(api_key=api_key)
            prompt = (
                f"根据关键词：{keywords}，生成工作日报。\n"
                f"格式要求：\n"
                f"1. [TOP5]部分：列出3-5条重要事项，纯文本，不带序号。\n"
                f"2. [总结]部分：一段简洁的总结（50字内）。\n"
                f"3. [TODO]部分：列出3-4条待办，纯文本，每行一条，不带序号。\n"
                f"4. 三个部分之间用 '@@@' 分隔。顺序必须是：TOP5@@@总结@@@TODO"
            )

            response = client.models.generate_content(model=GEMINI_MODEL_NAME, contents=prompt)
            content = response.text
            parts = content.split("@@@")
            self.root.after(0, lambda: self._update_ui_preview(parts))
            self.log("✅ AI 内容已生成，请在右侧预览区检查/修改！")
        except Exception as e:
            self.log(f"❌ 生成失败: {e}")

    def _update_ui_preview(self, parts):
        self.text_top5.delete("1.0", tk.END)
        self.text_summary.delete("1.0", tk.END)
        self.text_todo.delete("1.0", tk.END)
        if len(parts) > 0: self.text_top5.insert("1.0", parts[0].strip())
        if len(parts) > 1: self.text_summary.insert("1.0", parts[1].strip())
        if len(parts) > 2: self.text_todo.insert("1.0", parts[2].strip())
        self.btn_run.config(state="normal", text="🚀 确认内容无误，启动填写！")

    # ================= Selenium 执行 (最终修正版) =================
    def start_automation_thread(self):
        if not messagebox.askyesno("确认", "请确认浏览器已关闭，即将开始控制鼠标键盘填写？"):
            return
        threading.Thread(target=self._run_selenium, daemon=True).start()

    def _run_selenium(self):
        username = self.entry_user.get().strip()
        password = self.entry_pwd.get().strip()
        content_top5 = self.text_top5.get("1.0", tk.END).strip()
        content_summary = self.text_summary.get("1.0", tk.END).strip()
        content_todo_raw = self.text_todo.get("1.0", tk.END).strip()
        todo_list = [line for line in content_todo_raw.split('\n') if line.strip()]

        self.log("🌐 启动浏览器...")
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        try:
            driver = webdriver.Chrome(options=options)
            wait = WebDriverWait(driver, 20)
            
            driver.get(TARGET_URL)
            time.sleep(2)

            # --- 登录模块 ---
            try:
                try:
                    driver.find_element(By.CSS_SELECTOR, "div[data-type='paragraph']")
                    self.log("✅ 已登录")
                except:
                    self.log("🔒 执行自动登录...")
                    wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, '工号') or contains(@placeholder, '账号')]"))).send_keys(username)
                    wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, '密码')]"))).send_keys(password)
                    time.sleep(0.5)
                    btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), '登录')] | //input[@type='submit']")))
                    btn.click()
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-type='paragraph']")))
                    self.log("✅ 登录成功")
            except Exception as e:
                self.log(f"⚠️ 登录遇到阻碍: {e}")
                time.sleep(20)

            time.sleep(2)
            self.log("✍️ 开始填写表单...")

            # --- 1. Top 5 ---
            if self.var_top5.get():
                try:
                    potential_boxes = driver.find_elements(By.CSS_SELECTOR, "div[data-placeholder='请输入内容']")
                    target_box = None
                    for box in potential_boxes:
                        if box.is_displayed() and "ql-editor" not in box.get_attribute("class"):
                            target_box = box
                            break
                    
                    if target_box:
                        driver.execute_script("arguments[0].scrollIntoView(true);", target_box)
                        time.sleep(0.5)
                        current_text = target_box.text.strip()
                        if len(current_text) < 5 or "请输入内容" in current_text:
                            target_box.click()
                            time.sleep(0.2)
                            active = driver.switch_to.active_element
                            active.send_keys(Keys.CONTROL, "a")
                            active.send_keys(Keys.BACK_SPACE)
                            active.send_keys(Keys.DELETE)
                            time.sleep(0.2)
                            active.send_keys(content_top5)
                            self.log("   - [Top5] 填写完成")
                        else:
                            self.log("   - ✋ [Top5] 有内容，跳过")
                except Exception as e:
                    self.log(f"⚠️ [Top5] 错误: {str(e)[:50]}")

            # --- 2. 总结 ---
            if self.var_summary.get():
                try:
                    sm_box = driver.find_element(By.CSS_SELECTOR, "div.ql-editor[contenteditable='true']")
                    txt = sm_box.text.strip()
                    if len(txt) < 5 or "请输入内容" in txt:
                        self.clear_and_input(sm_box, content_summary)
                        self.log("   - [总结] 填写完成")
                    else:
                        self.log(f"   - ✋ [总结] 有内容，跳过")
                except:
                    self.log("⚠️ [总结] 填写失败")

            # --- 3. Todo ---
            if self.var_todo.get() and todo_list:
                try:
                    self.log(f"   - [Todo] 开始填写...")
                    for index, item in enumerate(todo_list):
                        all_inputs = driver.find_elements(By.CSS_SELECTOR, "div.tribute-input[contenteditable='true']")
                        target_input = None
                        for inp in all_inputs:
                            if inp.is_displayed():
                                if len(inp.text.strip()) < 2: 
                                    target_input = inp
                                    break
                        if not target_input:
                            try:
                                add_btn = driver.find_element(By.XPATH, "//*[contains(text(), '新增todo') or contains(text(), '新增待办')]")
                                add_btn.click()
                                time.sleep(0.5)
                                all_inputs = driver.find_elements(By.CSS_SELECTOR, "div.tribute-input[contenteditable='true']")
                                target_input = all_inputs[-1]
                            except: continue

                        if target_input:
                            target_input.click()
                            time.sleep(0.1)
                            target_input.send_keys(item)
                            time.sleep(0.2)
                            target_input.send_keys(Keys.ENTER) 
                            self.log(f"     -> 已填第 {index+1} 条")
                            time.sleep(0.5)
                    self.log("   - [Todo] 处理完毕")
                except Exception as e:
                    self.log(f"⚠️ [Todo] 错误: {e}")

            # --- 4. 保存 (强制点击版) ---
            self.log("💾 正在寻找保存按钮...")
            try:
                # 1. 强制滚动到底部
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

                # 2. 暴力查找
                # 您的截图显示按钮是蓝色的“保存”，通常是 <button> 或 <div role='button'>
                # 我们查找所有文本包含“保存”的元素
                xpath = "//*[text()='保存']" 
                buttons = driver.find_elements(By.XPATH, xpath)
                
                clicked = False
                for btn in buttons:
                    if btn.is_displayed():
                        # 排除掉一些奇怪的标签
                        if btn.tag_name in ['script', 'style', 'title']: continue
                        
                        self.log(f"🔍 找到潜在保存按钮: <{btn.tag_name}>")
                        
                        # 3. 强制 JS 点击 (穿透遮挡)
                        try:
                            driver.execute_script("arguments[0].click();", btn)
                            clicked = True
                            self.log(f"🎉 已强制点击保存！")
                            break
                        except Exception as e:
                            self.log(f"   点击尝试失败: {e}")
                
                if not clicked:
                    # 备用方案：找 class 包含 primary 的按钮 (通常蓝色按钮都有这个类)
                    self.log("⚠️ 文本定位失败，尝试样式定位...")
                    try:
                        primary_btn = driver.find_element(By.CSS_SELECTOR, "button[class*='primary'], div[class*='primary']")
                        driver.execute_script("arguments[0].click();", primary_btn)
                        self.log("🎉 通过样式找到并点击了保存！")
                    except:
                        self.log("❌ 彻底找不到保存按钮，请手动点击。")

            except Exception as e:
                self.log(f"⚠️ 保存流程出错: {e}")

            self.log("✅ 结束，20秒后关闭...")
            time.sleep(20)
            driver.quit()

        except Exception as e:
            self.log(f"❌ 严重错误: {e}")
            traceback.print_exc()

    def clear_and_input(self, element, text):
        try:
            element.click()
            time.sleep(0.2)
            element.send_keys(Keys.CONTROL, "a")
            element.send_keys(Keys.BACK_SPACE)
            time.sleep(0.2)
            element.send_keys(text)
        except:
            pass

if __name__ == "__main__":
    root = tk.Tk()
    app = TodoApp(root)
    root.mainloop()