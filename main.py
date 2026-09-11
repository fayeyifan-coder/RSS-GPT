import feedparser
import configparser
import os
import httpx
from openai import OpenAI
from jinja2 import Template
from bs4 import BeautifulSoup
import re
import datetime
import requests
from fake_useragent import UserAgent
import html
import smtplib
from email.mime.text import MIMEText
from email.header import Header

def get_cfg(sec, name, default=None):
    value = config.get(sec, name, fallback=default)
    if value:
        return value.strip('"')

config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')
secs = config.sections()

# 最大条目数限制
max_entries = 1000

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
U_NAME = os.environ.get('U_NAME')
OPENAI_PROXY = os.environ.get('OPENAI_PROXY')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
custom_model = os.environ.get('CUSTOM_MODEL')

# 邮件发送凭证
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.163.com')

deployment_url = f'https://{U_NAME}.github.io/RSS-GPT/'
BASE = get_cfg('cfg', 'BASE')
keyword_length = int(get_cfg('cfg', 'keyword_length', '5'))
summary_length = int(get_cfg('cfg', 'summary_length', '300'))
language = get_cfg('cfg', 'language', 'zh')

def fetch_feed(url, log_file):
    headers = {}
    try:
        ua = UserAgent()
        headers['User-Agent'] = ua.random.strip()
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            return {'feed': feed, 'status': 'success'}
        else:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Fetch error: {response.status_code}\n")
            return {'feed': None, 'status': response.status_code}
    except requests.RequestException as e:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"Fetch error: {e}\n")
        return {'feed': None, 'status': 'failed'}

def generate_untitled(entry):
    try: return entry.title
    except: 
        try: return entry.article[:50]
        except: return entry.link

def clean_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in ["script", "style", "img", "a", "video", "audio", "iframe", "input"]:
        for s in soup.find_all(tag):
            s.decompose()
    return soup.get_text()

def filter_entry(entry, filter_apply, filter_type, filter_rule):
    if filter_apply == 'title':
        text = entry.title
    elif filter_apply == 'article':
        text = entry.article
    elif filter_apply == 'link':
        text = entry.link
    elif not filter_apply:
        return True
    else:
        raise Exception('filter_apply not supported')

    if filter_type == 'include':
        return re.search(filter_rule, text, re.IGNORECASE)
    elif filter_type == 'exclude':
        return not re.search(filter_rule, text, re.IGNORECASE)
    elif filter_type == 'regex match':
        return re.search(filter_rule, text, re.IGNORECASE)
    elif filter_type == 'regex not match':
        return not re.search(filter_rule, text, re.IGNORECASE)
    elif not filter_type:
        return True
    else:
        raise Exception('filter_type not supported')

def read_entry_from_file(sec):
    out_dir = os.path.join(BASE, get_cfg(sec, 'name'))
    try:
        with open(out_dir + '.xml', 'r', encoding='utf-8') as f:
            rss = f.read()
        feed = feedparser.parse(rss)
        return feed.entries
    except:
        return []

def truncate_entries(entries, max_entries):
    if len(entries) > max_entries:
        entries = entries[:max_entries]
    return entries

def gpt_summary(query, model, language):
    # 强约束纯中文输出的提示词系统
    prompt_content = (
        f"你是一个专业的资讯提炼助手。请根据提供的文章内容，严格使用【中文】进行总结。\n"
        f"【严格要求】：\n"
        f"1. 即使原文是英文，摘要内容也必须完全翻译并提炼为中文，严禁输出英文段落或中英对照；\n"
        f"2. 人名、期刊名、机构名或专属物种名可保留英文原文；\n"
        f"3. 先提取 {keyword_length} 个中文关键词，在同一行内输出；\n"
        f"4. 然后换行，按顺序分要点用中文写一个 {summary_length} 字以内的核心总结；\n"
        f"5. 输出格式必须在总结主体前保留 '<br><br>总结:'。"
    )

    messages = [
        {"role": "system", "content": prompt_content},
        {"role": "user", "content": query}
    ]

    if not OPENAI_PROXY:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
    else:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
            http_client=httpx.Client(proxy=OPENAI_PROXY),
        )
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return completion.choices[0].message.content

def output(sec, language):
    log_file = os.path.join(BASE, get_cfg(sec, 'name') + '.log')
    out_dir = os.path.join(BASE, get_cfg(sec, 'name'))
    rss_urls = get_cfg(sec, 'url').split(',')

    filter_apply = get_cfg(sec, 'filter_apply')
    filter_type = get_cfg(sec, 'filter_type')
    filter_rule = get_cfg(sec, 'filter_rule')

    if not ((filter_apply and filter_type and filter_rule) or (not filter_apply and not filter_type and not filter_rule)):
        raise Exception('filter_apply, type, rule must be set together')

    max_items = int(get_cfg(sec, 'max_items') or 0)
    cnt = 0
    existing_entries = read_entry_from_file(sec)
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write('------------------------------------------------------\n')
        f.write(f'Started: {datetime.datetime.now()}\n')
        f.write(f'Existing_entries: {len(existing_entries)}\n')
        
    existing_entries = truncate_entries(existing_entries, max_entries=max_entries)
    append_entries = []
    last_valid_feed = None

    for rss_url in rss_urls:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"Fetching from {rss_url}\n")
            print(f"Fetching from {rss_url}")
        
        fetched = fetch_feed(rss_url, log_file)
        feed = fetched['feed']
        if not feed:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Fetch failed from {rss_url}\n")
            continue
        
        last_valid_feed = feed

        for entry in feed.entries:
            if cnt > max_entries:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Skip from: [{entry.title}]({entry.link})\n")
                break

            if entry.link.find('#replay') != -1 and entry.link.find('v2ex') != -1:
                entry.link = entry.link.split('#')[0]

            if entry.link in [x.link for x in existing_entries] or entry.link in [x.link for x in append_entries]:
                continue

            entry.title = generate_untitled(entry)

            try:
                entry.article = entry.content[0].value
            except:
                try: entry.article = entry.description
                except: entry.article = entry.title

            cleaned_article = clean_html(entry.article)

            if not filter_entry(entry, filter_apply, filter_type, filter_rule):
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Filter: [{entry.title}]({entry.link})\n")
                continue

            cnt += 1
            if cnt > max_items:
                entry.summary = None
            elif OPENAI_API_KEY:
                token_length = len(cleaned_article)
                target_model = custom_model if custom_model else "gpt-4o-mini"
                try:
                    entry.summary = gpt_summary(cleaned_article, model=target_model, language=language)
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"Token length: {token_length}\nSummarized using {target_model}\n")
                except Exception as e:
                    entry.summary = None
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"Summarization failed, error: {e}\n")

            append_entries.append(entry)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Append: [{entry.title}]({entry.link})\n")

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f'append_entries: {len(append_entries)}\n')

    # XML 渲染容错
    try:
        with open('template.xml', 'r', encoding='utf-8') as tf:
            template = Template(tf.read())
        
        feed_data = last_valid_feed if last_valid_feed else {"feed": {"title": get_cfg(sec, 'name')}}
        rss = template.render(feed=feed_data, append_entries=append_entries, existing_entries=existing_entries)
        
        with open(out_dir + '.xml', 'w', encoding='utf-8') as f:
            f.write(rss)
            
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'Finish: {datetime.datetime.now()}\n')
            
    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"error when rendering xml, skip {out_dir}: {e}\n")
            print(f"error when rendering xml, skip {out_dir}: {e}")

try:
    os.mkdir(BASE)
except:
    pass

feeds = []
links = []

for x in secs[1:]:
    output(x, language=language)
    feed = {"url": get_cfg(x, 'url').replace(',', '<br>'), "name": get_cfg(x, 'name')}
    feeds.append(feed)
    links.append("- " + get_cfg(x, 'url').replace(',', ', ') + " -> " + deployment_url + feed['name'] + ".xml\n")

def append_readme(readme, links):
    with open(readme, 'r', encoding='utf-8') as f:
        readme_lines = f.readlines()
    while readme_lines and (readme_lines[-1].startswith('- ') or readme_lines[-1] == '\n'):
        readme_lines = readme_lines[:-1]
    readme_lines.append('\n')
    readme_lines.extend(links)
    with open(readme, 'w', encoding='utf-8') as f:
        f.writelines(readme_lines)

append_readme("README.md", links)
append_readme("README-zh.md", links)

with open(os.path.join(BASE, 'index.html'), 'w', encoding='utf-8') as f:
    template = Template(open('template.html', encoding='utf-8').read())
    html_out = template.render(update_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), feeds=feeds)
    f.write(html_out)

# ----------------- 邮件推送逻辑 -----------------
def send_email_digest():
    if not MAIL_USERNAME or not MAIL_PASSWORD or not MAIL_SERVER:
        print("Missing email credentials (MAIL_USERNAME/MAIL_PASSWORD/MAIL_SERVER), skip sending email.")
        return

    print("Compiling email digest...")
    today_str = datetime.datetime.now().strftime('%Y年%m月%d日')
    email_html = f"<h2 style='color: #2c3e50;'>📰 每日学术与新闻早报（{today_str}）</h2><hr style='border:1px solid #eee;'>"
    has_content = False

    for x in secs[1:]:
        sec_name = get_cfg(x, 'name')
        xml_path = os.path.join(BASE, sec_name + '.xml')
        if not os.path.exists(xml_path):
            continue

        try:
            with open(xml_path, 'r', encoding='utf-8') as f:
                parsed = feedparser.parse(f.read())
                if parsed.entries:
                    has_content = True
                    email_html += f"<h3 style='color: #34495e; background: #f8f9fa; padding: 8px 12px; border-left: 4px solid #3498db;'>📌 {html.escape(sec_name)}</h3><ul style='list-style-type: none; padding-left: 0;'>"
                    
                    # 提取前 5 条最新内容发送
                    for entry in parsed.entries[:5]:
                        summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                        title = getattr(entry, 'title', 'Untitled')
                        link = getattr(entry, 'link', '#')
                        
                        email_html += f"<li style='margin-bottom: 18px; line-height: 1.6;'><a href='{link}' target='_blank' style='font-size: 16px; font-weight: bold; color: #1a0dab; text-decoration: none;'>{html.escape(title)}</a><br><div style='color: #333; margin-top: 6px;'>{summary}</div></li>"
                    email_html += "</ul>"
        except Exception as e:
            print(f"Error reading {xml_path} for email: {e}")

    if not has_content:
        print("No content available to send.")
        return

    msg = MIMEText(email_html, 'html', 'utf-8')
    msg['Subject'] = Header(f"【RSS 每日精选】{today_str}", 'utf-8')
    msg['From'] = MAIL_USERNAME
    msg['To'] = MAIL_USERNAME

    try:
        print(f"Connecting to SMTP server {MAIL_SERVER}...")
        try:
            server = smtplib.SMTP_SSL(MAIL_SERVER, 465, timeout=15)
        except Exception:
            server = smtplib.SMTP(MAIL_SERVER, 587, timeout=15)
            server.starttls()
            
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, [MAIL_USERNAME], msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

send_email_digest()
