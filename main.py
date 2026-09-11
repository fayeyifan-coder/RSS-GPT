import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
import feedparser
import requests  # 使用通用 HTTP 请求库调用 DeepSeek

# ==========================================
# AI 生成模块 (切换为 DeepSeek API)
# ==========================================


def generate_digest(prompt_text):
    """调用 DeepSeek API 生成早报"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("环境变量 DEEPSEEK_API_KEY 未设置")

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一位专业的学术与新闻早报编辑。",
            },
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0.3,
        "stream": False,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

# ==========================================
# 1. RSS 配置与防封抓取模块
# ==========================================

# 预设各大板块 RSS 源（中国特讯配置了多个备用源）
RSS_SOURCES = {
    "china": [
        "https://www.zaobao.com.sg/rss/realtime/china",
        "https://rss.thepaper.cn/rss/page/index?id=25950",
        "http://www.chinanews.com.cn/rss/scroll-news.xml",
    ],
    "world": [
        "https://www.theguardian.com/world/rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
    ],
    "nature": [
        "https://www.sciencedaily.com/rss/plants_animals/birds.xml",
        "https://phys.org/rss-feed/biology-news/ecology/",
    ],
    "humanities": [
        "https://aeon.co/feed.rss",
    ],
    "literature": [
        "https://www.literaryhub.com/feed/",
    ],
}


def fetch_rss_safely(url):
    """伪装请求头抓取 RSS，规避 403 / 503 及默认工具封禁"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            items = []
            for entry in feed.entries[:5]:  # 每个源提取前 5 条
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                items.append(f"- 标题: {title}\n  摘要: {summary[:200]}")
            return "\n".join(items)
    except Exception as e:
        print(f"[警告] 抓取失败 {url}: {e}")
    return ""


def get_category_content(urls):
    """轮询源列表，确保不为空"""
    if isinstance(urls, str):
        urls = [urls]

    aggregated_text = []
    for url in urls:
        content = fetch_rss_safely(url)
        if content:
            aggregated_text.append(content)

    return (
        "\n".join(aggregated_text)
        if aggregated_text
        else "（此板块今日未抓取到有效更新）"
    )


# ==========================================
# 2. 大模型 Prompt 构建与生成模块
# ==========================================


def build_prompt(china_text, world_text, nature_text, hum_text, lit_text):
    """构建带强约束力的 Prompt，防止语言漂移与版块遗漏"""
    return f"""
你是一位专业的学术与新闻早报编辑。请根据以下提取的 RSS 素材，整合并撰写一份精练、专业的《每日学术与新闻早报》。

【原始素材输入】
一、中国特讯：
{china_text}

二、国际新闻与实时动态：
{world_text}

三、鸟类生态与前沿研究：
{nature_text}

四、人文与社会深度：
{hum_text}

五、文学创作与全球新书：
{lit_text}

----------------------------------------
【绝对强制输出规则】
1. 全文 100% 简体中文：无论原始素材是英文还是其他语言，必须全部翻译并改写为通顺的简体中文。严禁保留大段英文原文。
2. 保留固定 5 大版块：必须严格使用上述 5 个板块名称作为二级标题。若某版块素材显示为无有效更新，请在标题下方保留一行“今日暂无更新。”，决不能直接删除标题。
3. 移除系统杂质与 AI 对话：
   - 严禁输出任何系统代码、标记标签（如、[source]、API 调试字符）。
   - 结尾严禁出现任何 AI 助手的问答式结语（如“您是否需要……”、“希望这份早报对您有帮助”等），请直接在最后一个新闻条目处自然结束。
4. 排版精炼：采用“粗体标题 + 1-2 句核心要点提炼”的结构，方便快速阅读。
"""


def generate_digest(prompt_text):
    """调用 Gemini API 生成早报"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("环境变量 GEMINI_API_KEY 未设置")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    response = model.generate_content(prompt_text)
    return response.text


# ==========================================
# 3. 邮件发送模块 (SMTP)
# ==========================================


def send_email(subject, content):
    """发送 HTML/纯文本邮件"""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.qq.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")  # 授权码或密码
    receiver_email = os.getenv("RECEIVER_EMAIL", sender_email)

    if not sender_email or not sender_password:
        print("[错误] 未配置发件人邮箱或密码/授权码，跳过邮件发送。")
        return

    message = MIMEText(content, "plain", "utf-8")
    message["From"] = Header(f"早报自动化 <{sender_email}>", "utf-8")
    message["To"] = Header(receiver_email, "utf-8")
    message["Subject"] = Header(subject, "utf-8")

    try:
        # 默认使用 SSL 连接 (465端口)，若是 587 端口可改为 SMTP + starttls
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()

        server.login(sender_email, sender_password)
        server.sendmail(sender_email, [receiver_email], message.as_string())
        server.quit()
        print("[成功] 早报邮件已顺利发送！")
    except Exception as e:
        print(f"[错误] 发送邮件失败: {e}")


# ==========================================
# 4. 主流程入口
# ==========================================


def main():
    print("[1/4] 开始抓取各板块 RSS 数据...")
    china_text = get_category_content(RSS_SOURCES["china"])
    world_text = get_category_content(RSS_SOURCES["world"])
    nature_text = get_category_content(RSS_SOURCES["nature"])
    hum_text = get_category_content(RSS_SOURCES["humanities"])
    lit_text = get_category_content(RSS_SOURCES["literature"])

    print("[2/4] 构建 Prompt 并调用 Gemini 模型...")
    prompt = build_prompt(
        china_text, world_text, nature_text, hum_text, lit_text
    )
    digest_result = generate_digest(prompt)

    print("[3/4] 早报生成完毕，准备发送...")
    # 获取当前日期作为标题
    from datetime import datetime

    today_str = datetime.now().strftime("%Y-%m-%d")
    email_subject = f"《每日学术与新闻早报》 {today_str}"

    print("[4/4] 正在发送邮件...")
    send_email(email_subject, digest_result)


if __name__ == "__main__":
    main()
