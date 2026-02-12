import os
import sys

# ================= 配置区域 =================
# 1. 安全读取 Key
# 解释：os.environ.get 意思是从系统环境变量里找。
# 如果找不到（比如你在本地跑），它就会报错或者用后面的默认值。
CRYPTO_PANIC_KEY = os.environ.get("CRYPTO_PANIC_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# 检查一下，如果 Key 没拿到，直接停止运行，防止报错
if not CRYPTO_PANIC_KEY or not GOOGLE_API_KEY:
    print("❌ 错误：未检测到 API Key！")
    print("   - 如果在 GitHub：请去 Settings -> Secrets 填入 Key")
    print("   - 如果在本地：请确保你没有把 os.environ 那行删掉")
    # 为了防止 GitHub Actions 里的测试报错，这里可以先不退出，或者由你决定
    # sys.exit(1)

# 2. 代理设置 (智能判断)
# GitHub 的服务器在美国，不需要代理。你本地需要。
if os.environ.get("GITHUB_ACTIONS"):
    print("☁️ 检测到在 GitHub 云端运行，使用直连模式...")
    PROXY_URL = None
    # 清除可能存在的代理干扰
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
else:
    print("🏠 检测到在本地运行，启用代理...")
    PROXY_URL = "http://127.0.0.1:7890" # 你的端口
    os.environ['HTTP_PROXY'] = PROXY_URL
    os.environ['HTTPS_PROXY'] = PROXY_URL

# ================= 文件路径定义  =================
HISTORY_FILE = "knowledge_base.json"
SENTIMENT_FILE = "sentiment_data.csv"
CHART_FILE = "sentiment_chart.png"
# ===============================================================
# ================= 模块 1: 基础工具 =================
def get_btc_price():
    """获取比特币当前价格 (用于对比情绪)"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        resp = requests.get(url, timeout=10)
        return resp.json()['bitcoin']['usd']
    except:
        return 0


def load_knowledge_base():
    """读取历史记忆 (简易版 RAG)"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_knowledge_base(new_entry, history):
    """保存今天的记忆"""
    history.append(new_entry)
    # 只保留最近 30 天的记忆，防止文件太大
    if len(history) > 30:
        history = history[-30:]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def find_relevant_history(history, current_news_titles):
    """
    RAG 核心：检索相关历史。
    这里用最简单的关键词匹配，高级玩家可以用 Vector DB。
    """
    context = ""
    keywords = ["Hack", "ETF", "SEC", "Upgrade", "Fork", "Rate"]  # 敏感词

    found_count = 0
    for past_item in history[-7:]:  # 只看过去7天
        past_summary = past_item.get('summary', '')
        # 如果历史记录里包含当前的敏感词
        for kw in keywords:
            if kw in current_news_titles and kw in past_summary:
                context += f"- {past_item['date']}: {past_summary[:50]}...\n"
                found_count += 1
                break

    if context:
        return f"【历史记忆回溯】(AI 发现以前发生过类似的事):\n{context}"
    return "【历史记忆】暂无强相关历史事件。"


# ================= 模块 2: 核心逻辑 =================

def run_daily_analysis():
    print("🚀 启动超级分析机器人...")

    # 1. 抓新闻 (复用之前的逻辑)
    # ... (为了节省篇幅，这里假设你已经有了 news_data) ...
    # 实际跑的时候请把之前的 get_filtered_news 函数粘贴进来使用
    # 这里用假数据演示流程:
    news_data = [{"title": "Bitcoin surges past 100k", "votes": {"positive": 50}}]

    # 2. 准备上下文
    history = load_knowledge_base()
    titles_text = " ".join([n['title'] for n in news_data])
    rag_context = find_relevant_history(history, titles_text)
    btc_price = get_btc_price()

    # 3. AI 分析 (Prompt 升级)
    client = genai.Client(api_key=GOOGLE_API_KEY)

    prompt = f"""
    你是顶级加密货币分析师。

    今日新闻: {news_data}
    当前BTC价格: ${btc_price}

    {rag_context} (这是你过去几天的记忆，如果有相关性请在分析中引用)

    请完成两个任务：

    任务一：JSON 格式打分 (这是必须的，严禁Markdown格式，只输出JSON)
    {{
        "sentiment_score": (0-100的整数, 0是极度恐慌, 100是极度贪婪),
        "summary": "一句话总结今日市场核心叙事"
    }}

    任务二：深度研报 (另起一行)
    ... (这里写你之前的研报格式) ...
    """

    # ... 调用 Gemini (用 flash-2.0 或 1.5) ...
    # 假设 AI 返回了 response.text
    # 这里为了演示，我们手动模拟 AI 的返回
    ai_response_json = {"sentiment_score": 75, "summary": "ETF通过预期推动市场上涨"}

    # 4. 保存数据 (挑战 A：数据持久化)
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # 存 CSV
    new_row = {"date": today, "price": btc_price, "score": ai_response_json['sentiment_score']}
    if os.path.exists(SENTIMENT_FILE):
        df = pd.read_csv(SENTIMENT_FILE)
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        df = pd.DataFrame([new_row])
    df.to_csv(SENTIMENT_FILE, index=False)

    # 存 JSON (挑战 B：记忆持久化)
    save_knowledge_base({"date": today, "summary": ai_response_json['summary']}, history)

    print("✅ 数据已保存到 CSV 和 JSON。")
    return df


# ================= 模块 3: 可视化 (挑战 A) =================

def generate_chart(df):
    """画图：双轴图 (左边价格，右边情绪)"""
    if len(df) < 2:
        print("⚠️ 数据不够，明天再画图。")
        return

    print("🎨 正在绘制趋势图...")
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # X轴：日期
    dates = pd.to_datetime(df['date'])

    # 左轴：币价 (蓝色)
    color = 'tab:blue'
    ax1.set_xlabel('Date')
    ax1.set_ylabel('BTC Price ($)', color=color)
    ax1.plot(dates, df['price'], color=color, marker='o', label='Price')
    ax1.tick_params(axis='y', labelcolor=color)

    # 右轴：情绪 (红色)
    ax2 = ax1.twinx()
    color = 'tab:red'
    ax2.set_ylabel('AI Sentiment (0-100)', color=color)
    ax2.plot(dates, df['score'], color=color, linestyle='--', marker='x', label='Sentiment')
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.set_ylim(0, 100)  # 情绪固定 0-100

    plt.title('Bitcoin Price vs AI Sentiment Analysis')
    fig.tight_layout()
    plt.savefig(CHART_FILE)
    print(f"🖼️ 图表已生成: {CHART_FILE}")


# ================= 主程序 =================
if __name__ == "__main__":
    df = run_daily_analysis()

    generate_chart(df)
