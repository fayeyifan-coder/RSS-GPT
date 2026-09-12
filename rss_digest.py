import os
import re
from bs4 import BeautifulSoup
import feedparser
import requests

# 自动读取环境变量（优先使用仓库里配置好的变量名）
API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1").rstrip(
    "/"
)
MODEL = os.getenv("CUSTOM_MODEL", "deepseek-chat")
BARK_KEY = os.getenv("BARK_KEY")

# 自定义 RSS 订阅源（可随时修改或增加）
RSS_SOURCES = {
    "Nature Ecology": "https://www.nature.com/natecolevol.rss",
    "Science Daily Ecology": "https://www.sciencedaily.com/rss/top/environment.xml",
}

MAX_ITEMS_PER_FEED = 2


def clean_html(raw_html):
    """提取纯文本，去除网页标签"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def summarize_with_ai(title, content):
    """调用大模型提炼 80 字中文摘要与标题"""
    if not API_KEY:
        print("[警告] 未检测到 API Key，跳过 AI 处理")
        return f"【{title}】\n{content[:80]}..."

    prompt = f"""请阅读以下英文学术新闻，将其总结并翻译为中文：
1. 第一行为精简中文标题（不要加“标题：”前缀）。
2. 第二行为 80 字以内的中文核心摘要（不要加“摘要：”前缀）。

原文标题：{title}
原文内容：{content[:800]}"""

    # 格式化 API 请求地址
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
            return res.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"[错误] API 响应失败 [{res.status_code}]: {res.text}")
    except Exception as e:
        print(f"[错误] 请求 AI 接口失败: {e}")

    return f"【{title}】\n{content[:80]}..."


def send_bark(title, content):
    """推送极简速递到 Bark"""
    if not BARK_KEY:
        print("[错误] 缺失 BARK_KEY 环境变量，无法推送")
        return

    url = f"https://api.day.app/{BARK_KEY}"
    payload = {
        "title": title,
        "body": content,
        "group": "学术速递",
        "icon": "https://cdn-icons-png.flaticon.com/512/2965/2965358.png",
    }
    try:
        res = requests.post(url, json=payload, timeout=10).json()
        if res.get("code") == 200:
            print("[成功] 已成功推送到 Bark！")
        else:
            print(f"[失败] Bark 响应错误: {res}")
    except Exception as e:
        print(f"[错误] 发送 Bark 请求异常: {e}")


def main():
    results = []
    for source_name, feed_url in RSS_SOURCES.items():
        print(f"正在抓取订阅源: {source_name}...")
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            title = entry.get("title", "")
            summary = clean_html(
                entry.get("summary", entry.get("description", ""))
            )

            ai_text = summarize_with_ai(title, summary)
            results.append(f"📌 {source_name}\n{ai_text}")

    if results:
        content = "\n\n".join(results)
        send_bark("📰 每日精选学术速递", content)
    else:
        print("[提示] 未抓取到有效文章数据")


if __name__ == "__main__":
    main()
