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
MAIL_USERNAME = os.getenv("MAIL_USERNAME")  # 发件人邮箱 (如 xxx@qq.com)
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")  # 邮箱授权码/密码
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.qq.com")  # SMTP 服务器地址
RECEIVER_EMAIL = os.getenv("U_NAME", MAIL_USERNAME)  # 收件人邮箱（默认同发件人）

# 订阅源配置
RSS_SOURCES = {
    "Nature Ecology": "https://www.nature.com/natecolevol.rss",
    "Science Daily Ecology": "https://www.sciencedaily.com/rss/top/environment.xml",
}

MAX_ITEMS_PER_FEED = 3  # 改用邮件后可以多放几条新闻


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

    prompt = f"""请阅读以下英文学术新闻，将其总结并翻译为中文：
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
                f"<h3 style='color: #2c3e50; margin-bottom: 5px;'>{zh_title}</h3>"
                f"<p style='color: #555; line-height: 1.6; margin-top: 0;'>{zh_summary}</p>"
            )
        else:
            print(f"[错误] API 响应失败 [{res.status_code}]: {res.text}")
    except Exception as e:
        print(f"[错误] 请求 AI 接口失败: {e}")

    return f"<h3>{title}</h3><p>{content[:150]}...</p>"


def send_email(subject, html_content):
    """发送 HTML 格式邮件"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[错误] 缺失 MAIL_USERNAME 或 MAIL_PASSWORD 环境变量，无法发送邮件")
        return

    message = MIMEText(html_content, "html", "utf-8")
    message["From"] = Header(f"学术速递助手 <{MAIL_USERNAME}>", "utf-8")
    message["To"] = Header(RECEIVER_EMAIL, "utf-8")
    message["Subject"] = Header(subject, "utf-8")

    try:
        # 465 端口 SSL 连接 (QQ/163 等常见邮箱端口)
        server = smtplib.SMTP_SSL(MAIL_SERVER, 465, timeout=15)
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, [RECEIVER_EMAIL], message.as_string())
        server.quit()
        print("[成功] 每日学术速递已成功发送至邮箱！")
    except Exception as e:
        print(f"[错误] 发送邮件失败: {e}")


def main():
    email_items = []
    for source_name, feed_url in RSS_SOURCES.items():
        print(f"正在抓取订阅源: {source_name}...")
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            title = entry.get("title", "")
            link = entry.get("link", "#")
            summary = clean_html(
                entry.get("summary", entry.get("description", ""))
            )

            ai_html = summarize_with_ai(title, summary)
            item_card = f"""
            <div style="background: #f9f9f9; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #3498db;">
                <span style="font-size: 12px; background: #e0e0e0; padding: 2px 6px; border-radius: 4px; color: #333;">📌 {source_name}</span>
                {ai_html}
                <a href="{link}" style="color: #3498db; text-decoration: none; font-size: 14px;">👉 阅读原文</a>
            </div>
            """
            email_items.append(item_card)

    if email_items:
        full_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 650px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px;">📰 每日精选学术速递</h2>
            {"".join(email_items)}
            <p style="font-size: 12px; color: #999; text-align: center;">由 GitHub Actions 自动化脚本生成</p>
        </body>
        </html>
        """
        send_email("📰 每日精选学术速递", full_body)
    else:
        print("[提示] 未抓取到有效文章数据")


if __name__ == "__main__":
    main()
