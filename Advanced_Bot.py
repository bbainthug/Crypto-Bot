import os
import sys
import json
import requests
import pandas as pd
import matplotlib.pyplot as plt
import datetime
# 引入 Google 官方稳定版库
import google.generativeai as genai

# ================= 1. 配置区域 =================
# 自动读取环境变量 (GitHub Secrets)
CRYPTO_PANIC_KEY = os.environ.get("CRYPTO_PANIC_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# 文件路径定义 (Copilot 提到的重点)
HISTORY_FILE = "knowledge_base.json"
SENTIMENT_FILE = "sentiment_data.csv"
CHART_FILE = "sentiment_chart.png"

# 代理设置 (智能判断环境)
if os.environ.get("GITHUB_ACTIONS"):
    print("☁️ 检测到在 GitHub 云端运行，使用直连模式...")
    PROXY_URL = None
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
else:
    print("🏠 检测到在本地运行，启用代理...")
    PROXY_URL = "http://127.0.0.1:7890" 
    os.environ['HTTP_PROXY'] = PROXY_URL
    os.environ['HTTPS_PROXY'] = PROXY_URL

# ================= 2. 基础工具函数 =================

def get_btc_price():
    """获取比特币当前价格"""
    try:
        # 使用 CoinGecko 免费 API
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        resp = requests.get(url, timeout=10)
        price = resp.json()['bitcoin']['usd']
        print(f"💰 当前 BTC 价格: ${price}")
        return price
    except Exception as e:
        print(f"⚠️ 无法获取价格: {e}")
        return 0

def get_real_news(limit=20):
    """【恢复真实数据】从 CryptoPanic 抓取新闻"""
    if not CRYPTO_PANIC_KEY:
        print("❌ 缺少 CryptoPanic Key，无法抓取新闻！")
        return []
        
    print(f"📡 正在连接 CryptoPanic (v2 API)...")
    base_url = "https://cryptopanic.com/api/developer/v2/posts/"
    full_url = f"{base_url}?auth_token={CRYPTO_PANIC_KEY}&public=true&filter=rising&regions=en"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    try:
        response = requests.get(full_url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            print(f"✅ 成功抓取 {len(results)} 条新闻。")
            return results[:limit]
        else:
            print(f"❌ CryptoPanic 请求失败: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ 网络错误: {e}")
        return []

def load_knowledge_base():
    """读取历史记忆 (JSON)"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_knowledge_base(new_entry, history):
    """保存今日记忆"""
    history.append(new_entry)
    # 只保留最近 30 天，防止文件无限膨胀
    if len(history) > 30: history = history[-30:]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def find_relevant_history(history, current_news_titles):
    """RAG 检索：看看历史上有没有类似的事"""
    context = ""
    # 简单的关键词匹配
    keywords = ["Hack", "ETF", "SEC", "Upgrade", "Fork", "Rate", "Ban"]
    
    # 检查最近 7 天的记忆
    for past_item in history[-7:]:
        past_summary = past_item.get('summary', '')
        past_date = past_item.get('date', 'Unknown')
        
        # 只要当前新闻标题和历史摘要里有同一个敏感词，就提取出来
        for kw in keywords:
            if kw in current_news_titles and kw in past_summary:
                context += f"- [{past_date}] 曾发生: {past_summary[:50]}...\n"
                break # 只要匹配到一个词就够了
                
    return context if context else "暂无强相关历史事件。"

# ================= 3. 核心分析逻辑 =================

def run_daily_analysis():
    print("🚀 启动分析引擎...")
    
    # 1. 准备 Gemini
    if not GOOGLE_API_KEY:
        print("❌ 缺少 Google API Key，无法分析！")
        return None
    
    genai.configure(api_key=GOOGLE_API_KEY)
    
    # 2. 获取真实数据
    news_list = get_real_news(limit=15)
    if not news_list:
        print("⚠️ 没有抓到新闻，任务终止。")
        return None
        
    btc_price = get_btc_price()
    
    # 3. 准备 RAG 上下文
    history = load_knowledge_base()
    all_titles = " ".join([n.get('title','') for n in news_list])
    rag_context = find_relevant_history(history, all_titles)
    
    print(f"🧠 历史记忆检索结果: \n{rag_context}")

    # 4. 构建 Prompt (提示词)
    # 我们把新闻列表处理成字符串，节省 Token
    news_text = "\n".join([f"- {n.get('title', '')} (Votes: {n.get('votes', {}).get('positive', 0)})"for n in news_list])

    prompt = f"""
    你是华尔街顶级的加密货币分析师。
    
    【今日数据】
    - BTC价格: ${btc_price}
    - 市场新闻: 
    {news_text}
    
    【历史参考 (RAG)】
    {rag_context}
    
    请根据以上信息，完成以下任务。必须严格遵守输出格式。

    任务 1：计算“AI 恐慌/贪婪指数” (0-100)
    - 0 是极度恐慌，100 是极度贪婪。
    - 参考新闻的情绪投票和 BTC 价格表现。

    任务 2：一句话总结今日叙事。

    请直接返回 JSON 格式数据 (不要 Markdown 代码块)：
    {{"sentiment_score": 75, "summary": "这里写你的总结"}}
    """
    
    # 5. 调用 AI
    try:
        print("🤖 正在请求 Gemini-3-flash-preview...")
        model = genai.GenerativeModel('gemini-3-flash-preview')
        response = model.generate_content(prompt)
        
        # 清洗返回数据 (去掉可能存在的 ```json )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"): text = text[:-3]
        
        ai_data = json.loads(text)
        print(f"✅ AI 分析完成! 分数: {ai_data['sentiment_score']}")
        
    except Exception as e:
        print(f"❌ AI 分析出错: {e}")
        # 出错时的默认值，保证数据流不断
        ai_data = {"sentiment_score": 50, "summary": "AI 分析暂时不可用"}

    # 6. 数据持久化 (存 CSV 和 JSON)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 存 CSV (用于画图)
    new_row = {
        "date": today, 
        "price": btc_price, 
        "score": ai_data.get('sentiment_score', 50)
    }
    
    if os.path.exists(SENTIMENT_FILE):
        df = pd.read_csv(SENTIMENT_FILE)
        # 修复 pandas 警告，使用 pd.concat
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        df = pd.DataFrame([new_row])
    
    # 去重：如果同一天跑了多次，只保留最后一次
    df.drop_duplicates(subset=['date'], keep='last', inplace=True)
    df.to_csv(SENTIMENT_FILE, index=False)
    
    # 存 JSON (用于记忆)
    save_knowledge_base({
        "date": today, 
        "summary": ai_data.get('summary', 'No summary')
    }, history)
    
    print("💾 数据已保存到本地。")
    return df

# ================= 4. 可视化 (双轴图表) =================

def generate_chart(df):
    """【恢复高级图表】绘制 双轴图 (价格 vs 情绪)"""
    if df is None or len(df) < 1:
        print("⚠️ 数据不足，跳过画图。")
        return

    print("🎨 正在绘制双轴趋势图...")
    
    # 设置风格
    plt.style.use('seaborn-v0_8-darkgrid' if 'seaborn-v0_8-darkgrid' in plt.style.available else 'ggplot')
    
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # X轴处理
    dates = pd.to_datetime(df['date'])

    # 左轴：币价 (蓝色实线)
    color_price = 'tab:blue'
    ax1.set_xlabel('Date')
    ax1.set_ylabel('BTC Price ($)', color=color_price, fontweight='bold')
    ax1.plot(dates, df['price'], color=color_price, marker='o', linewidth=2, label='Price')
    ax1.tick_params(axis='y', labelcolor=color_price)

    # 右轴：情绪 (红色虚线)
    ax2 = ax1.twinx()  
    color_sent = 'tab:red'
    ax2.set_ylabel('AI Sentiment (0-100)', color=color_sent, fontweight='bold')
    ax2.plot(dates, df['score'], color=color_sent, linestyle='--', marker='x', linewidth=2, label='Sentiment')
    ax2.tick_params(axis='y', labelcolor=color_sent)
    ax2.set_ylim(0, 100) # 固定 0-100 范围
    
    # 添加参考线 (50分是中性)
    ax2.axhline(50, color='gray', linestyle=':', alpha=0.5)

    plt.title('Bitcoin Price vs AI Sentiment Trend', fontsize=14)
    fig.tight_layout()
    
    plt.savefig(CHART_FILE)
    print(f"🖼️ 图表已生成: {CHART_FILE}")

# ================= 5. 程序入口 =================
if __name__ == "__main__":
    # 1. 运行分析
    df = run_daily_analysis()
    
    # 2. 如果分析成功，绘制图表
    if df is not None:
        generate_chart(df)


