import os
import re
from bs4 import BeautifulSoup
import feedparser
import requests

# 环境变量读取
LLM_API_KEY = os.getenv("LLM_API_KEY")
# 默认使用 DeepSeek 官方 API 地址，也可替换为 SiliconFlow 或 OpenAI 兼容地址
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# 订阅源配置（可自行替换/增删）
RSS_SOURCES = {
    "Nature Ecology": "https://www.nature.com/natecolevol.rss",
    "Science Daily Ecology": "https://www.sciencedaily.com/rss/top/environment.xml",
}

# 每个订阅源每日最多抓取条数
MAX_ITEMS_PER_FEED = 2


def clean_html(raw_html):
    """去除 RSS 正文中的 HTML 标签与格式杂质"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def summarize_and_translate_with_ai(title, content):
    """调用 LLM 进行自动翻译与 80 字极简摘要提炼"""
    if not LLM_API_KEY:
        print("[警告] 未配置 LLM_API_KEY，跳过 AI 提炼")
        return f"**{title}**\n{content[:100]}..."

    prompt = f"""
你是一个专业科研与新闻速递助理。请阅读以下新闻标题和正文，将其翻译并总结为中文。

【要求】
1. 生成一个精准简练的中文标题（不要添加“标题：”前缀）。
2. 提供一段不超过 80 字的中文核心摘要，说明研究/新闻的核心结论或事件（不要添加“摘要：”前缀）。
3. 语气客观专业，禁止罗列废话。

【原文标题】：{title}
【原文内容】：{content[:800]}

【输出格式】：
[中文标题]
[中文核心摘要]
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
        response = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"].strip()
            return result
        else:
            print(f"[错误] API 返回异常: HTTP {response.status_code}")
    except Exception as e:
        print(f"[错误] 请求 LLM 接口失败: {e}")

    # 接口失败时的后备处理
    return f"**{title}**\n{content[:100]}..."


def fetch_and_process_rss():
    digest_results = []

    for source_name, feed_url in RSS_SOURCES.items():
        print(f"正在抓取源: {source_name}...")
        feed = feedparser.parse(feed_url)

        entries = feed.entries[:MAX_ITEMS_PER_FEED]
        for entry in entries:
            title = entry.get("title", "")
            raw_summary = entry.get("summary", entry.get("description", ""))
            clean_summary = clean_html(raw_summary)
            link = entry.get("link", "")

            # 调用 AI 处理
            processed_content = summarize_and_translate_with_ai(
                title, clean_summary
            )

            digest_results.append(
                {"source": source_name, "content": processed_content, "url": link}
            )

    return digest_results


def generate_markdown(digest_list):
    """生成排版优雅的全局速递文本"""
    md_output = "# 📰 每日精选科研与学术速递\n\n"
    for item in digest_list:
        md_output += f"### [{item['source']}] \n"
        md_output += f"{item['content']}\n"
        md_output += f"[👉 阅读原文]({item['url']})\n\n"
        md_output += "---\n\n"
    return md_output


def main():
    digests = fetch_and_process_rss()
    final_report = generate_markdown(digests)

    # 打印最终生成的短精炼速递（可直接对接发送邮件或推送脚本）
    print("=" * 20 + " 生成简报结果 " + "=" * 20)
    print(final_report)


if __name__ == "__main__":
    main()
