import google.generativeai as genai

# --- 请在这里填入你的 API Key ---
api_key = input("请输入你的 Google API Key 并回车: ")

# 配置 API
try:
    genai.configure(api_key=api_key)
    
    print("\n正在连接 Google 服务器查询可用模型...\n")
    print("-" * 50)
    print(f"{'模型名称 (Model Name)':<40} | {'说明'}")
    print("-" * 50)

    # 获取所有模型列表
    count = 0
    for m in genai.list_models():
        # 我们只关心能生成内容 (generateContent) 的模型
        if 'generateContent' in m.supported_generation_methods:
            # 过滤掉老旧模型，只看 Gemini 系列
            if "gemini" in m.name:
                print(f"{m.name:<40} | {m.display_name}")
                count += 1
    
    print("-" * 50)
    print(f"\n查询完成！共找到 {count} 个可用 Gemini 模型。")
    print("请使用上面列出的 'name' (例如 models/gemini-1.5-flash) 填入代码中。")

except Exception as e:
    print("\n查询失败！可能是网络问题或 API Key 错误。")
    print(f"错误信息: {e}")

input("\n按回车键退出...")