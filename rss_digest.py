import os
import re
from bs4 import BeautifulSoup
import feedparser
import requests

# 环境变量读取
LLM_API_KEY = os.getenv("LLM_API_KEY")
BARK_KEY = os.getenv("BARK_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# 订阅源配置
RSS_SOURCES = {
    "Nature Ecology": "https://www.nature.com/natecolevol.rss",
    "Science Daily Ecology": "https://www.sciencedaily.com/rss/top/environment.xml",
}

MAX_ITEMS_PER_FEED = 2


def clean_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def summarize_and_translate_with_ai(title, content):
    if not LLM_API_KEY:
        print("[警告] 未配置 LLM_API_KEY，跳过 AI 提炼")
        return f"【{title}】\n{content[:80]}..."

    prompt = f"""
请阅读以下英文学术新闻，将其总结并翻译为中文。

【要求】
1. 第一行为中文标题（不要加“标题：”前缀）。
2. 第二行为 80 字以内的中文核心摘要（不要加“摘要：”前缀）。

【原文标题】：{title}
【原文内容】：{content[:800]}
"""

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }

    try:
        res = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[错误] AI 处理失败: {e}")

    return f"【{title}】\n{content[:80]}..."


def send_bark(title, content):
    """推送到 Bark"""
    if not BARK_KEY:
        print("[错误] 缺失 BARK_KEY，无法推送")
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
            print("[成功] 学术速递已成功推送到 Bark！")
        else:
            print(f"[失败] Bark 响应异常: {res}")
    except Exception as e:
        print(f"[错误] Bark 推送请求失败: {e}")


def main():
    digests = []
    for source_name, feed_url in RSS_SOURCES.items():
        print(f"抓取中: {source_name}...")
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            title = entry.get("title", "")
            raw_summary = entry.get("summary", entry.get("description", ""))
            clean_text = clean_html(raw_summary)

            ai_result = summarize_and_translate_with_ai(title, clean_text)
            digests.append(f"📌 {source_name}\n{ai_result}")

    if digests:
        final_content = "\n\n".join(digests)
        send_bark("📰 每日精选学术速递", final_content)


if __name__ == "__main__":
    main()
