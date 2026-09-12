import os
import re
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import feedparser
import requests

# 环境变量读取
API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1").rstrip(
    "/"
)
MODEL = os.getenv("CUSTOM_MODEL", "deepseek-chat")

# 邮件配置
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.qq.com")
RECEIVER_EMAIL = os.getenv("U_NAME", MAIL_USERNAME)

# 全局多分类 RSS 订阅源配置
RSS_CATEGORIES = {
    "🌿 生态与鸟类": {
        "Nature Ecology": "https://www.nature.com/natecolevol.rss",
        "Science Daily Ecology": "https://www.sciencedaily.com/rss/top/environment.xml",
    },
    "🌍 国际新闻": {
        "BBC News World": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "Reuters World": "https://www.reutersagency.com/feed/?best-topics=world-news&post_type=best",
    },
    "📚 人文社会": {
        "Aeon Essays": "https://aeon.co/feed.rss",
        "The New Yorker": "https://www.newyorker.com/feed/everything",
    },
    "🤖 AI 与科技": {
        "MIT Tech Review": "https://www.technologyreview.com/feed/",
        "TechCrunch": "https://techcrunch.com/feed/",
    },
}

MAX_ITEMS_PER_FEED = 1  # 保持各源精选，控制邮件整体篇幅


def clean_html(raw_html):
    """提取纯文本，去除网页标签"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def summarize_with_ai(title, content):
    """调用大模型提炼 100 字中文摘要与标题"""
    if not API_KEY:
        print("[警告] 未检测到 API Key，跳过 AI 处理")
        return f"<h3>{title}</h3><p>{content[:150]}...</p>"

    prompt = f"""请阅读以下新闻或文章，将其总结并翻译为中文：
1. 第一行为精简中文标题（不要加“标题：”前缀）。
2. 第二行为 100 字以内的中文核心摘要（不要加“摘要：”前缀）。

原文标题：{title}
原文内容：{content[:800]}"""

    url = (
        f"{BASE_URL}/chat/completions"
        if not BASE_URL.endswith("/chat/completions")
        else BASE_URL
    )
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            text = res.json()["choices"][0]["message"]["content"].strip()
            lines = [line for line in text.split("\n") if line.strip()]
            zh_title = lines[0] if lines else title
            zh_summary = (
                "<br>".join(lines[1:])
                if len(lines) > 1
                else "（无进一步摘要）"
            )
            return (
                f"<h4 style='color: #2c3e50; margin: 5px 0;'>{zh_title}</h4>"
                f"<p style='color: #555; line-height: 1.6; font-size: 14px; margin: 5px 0;'>{zh_summary}</p>"
            )
        else:
            print(f"[错误] API 响应失败 [{res.status_code}]: {res.text}")
    except Exception as e:
        print(f"[错误] 请求 AI 接口失败: {e}")

    return f"<h4>{title}</h4><p>{content[:150]}...</p>"


def send_email(subject, html_content):
    """发送 HTML 格式邮件"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[错误] 缺失 MAIL_USERNAME 或 MAIL_PASSWORD 环境变量")
        return

    message = MIMEText(html_content, "html", "utf-8")
    message["From"] = Header(f"全局资讯速递 <{MAIL_USERNAME}>", "utf-8")
    message["To"] = Header(RECEIVER_EMAIL, "utf-8")
    message["Subject"] = Header(subject, "utf-8")

    try:
        server = smtplib.SMTP_SSL(MAIL_SERVER, 465, timeout=15)
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, [RECEIVER_EMAIL], message.as_string())
        server.quit()
        print("[成功] 每日多领域速递已发送至邮箱！")
    except Exception as e:
        print(f"[错误] 发送邮件失败: {e}")


def main():
    category_html_blocks = []

    for cat_name, feeds in RSS_CATEGORIES.items():
        print(f"正在处理分类: {cat_name}...")
        feed_items = []

        for source_name, feed_url in feeds.items():
            print(f"  └─ 抓取源: {source_name}")
            feed = feedparser.parse(feed_url)

            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                title = entry.get("title", "")
                link = entry.get("link", "#")
                summary = clean_html(
                    entry.get("summary", entry.get("description", ""))
                )

                ai_html = summarize_with_ai(title, summary)
                item_card = f"""
                <div style="background: #ffffff; padding: 12px; border-radius: 6px; margin-bottom: 12px; border: 1px solid #e1e8ed;">
                    <span style="font-size: 11px; background: #e8f4f8; color: #1da1f2; padding: 2px 6px; border-radius: 4px;">{source_name}</span>
                    {ai_html}
                    <a href="{link}" style="color: #3498db; text-decoration: none; font-size: 13px;">👉 阅读原文</a>
                </div>
                """
                feed_items.append(item_card)

        if feed_items:
            cat_block = f"""
            <div style="margin-bottom: 25px;">
                <h3 style="color: #1a2a3a; border-left: 4px solid #3498db; padding-left: 10px; margin-bottom: 12px;">{cat_name}</h3>
                {"".join(feed_items)}
            </div>
            """
            category_html_blocks.append(cat_block)

    if category_html_blocks:
        full_body = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 680px; margin: 0 auto; padding: 20px; background-color: #f4f7f9;">
            <div style="background: #ffffff; padding: 25px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                <h2 style="color: #2c3e50; text-align: center; border-bottom: 2px solid #eee; padding-bottom: 15px; margin-top: 0;">📰 每日全局情报速递</h2>
                {"".join(category_html_blocks)}
                <p style="font-size: 12px; color: #aaa; text-align: center; margin-top: 30px;">由 GitHub Actions 自动化脚本生成</p>
            </div>
        </body>
        </html>
        """
        send_email("📰 每日全局情报速递 (生态/国际/人文/AI)", full_body)
    else:
        print("[提示] 未抓取到有效文章数据")


if __name__ == "__main__":
    main()
