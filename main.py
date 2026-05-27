"""
AI 早报自动推送系统
每天早上 7:00 通过 GitHub Actions 自动运行，抓取 AI+科技新闻，
生成文字摘要和 TTS 语音，通过 Bark 推送到 iPhone。
"""
import asyncio  # 异步 IO 支持，用于并发网络请求
import os  # 读取环境变量
import json  # 解析 JSON 数据
import re  # 正则表达式，清理 HTML 标签
import hashlib  # 生成哈希，用于标题去重
import time  # 时间戳相关
from datetime import datetime, timezone, timedelta  # 日期时间处理
from pathlib import Path  # 文件路径操作
from urllib.parse import urlencode  # URL 参数编码

import httpx  # 异步 HTTP 客户端，用于 API 请求和 Bark 推送
import feedparser  # RSS 解析库
import edge_tts  # 微软 Edge TTS，免费文字转语音


# ============================================================
# 配置区
# ============================================================
BARK_KEY = os.environ.get("BARK_KEY", "iFrHTEy9BhfdYxaX2dFD5k")  # Bark 推送密钥
BARK_BASE = f"https://api.day.app/{BARK_KEY}"  # Bark API 基础地址
PAGES_URL = os.environ.get("PAGES_URL", "")  # GitHub Pages 地址（运行时自动获取）
OUTPUT_DIR = Path("output")  # 输出目录，存放生成的 mp3
MP3_FILE = "news.mp3"  # 语音文件名
MAX_NEWS = 15  # 最多推送的新闻条数
TTS_VOICE = "zh-CN-XiaoxiaoNeural"  # TTS 语音：中文女声，自然流畅
BARK_GROUP = "AI早报"  # Bark 通知分组
BARK_ICON = "https://raw.githubusercontent.com/bark-server/bark/main/Assets/icon.png"  # 通知图标

# HTTP 请求头，模拟浏览器避免被反爬
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def get_beijing_time():
    """获取当前北京时间字符串，格式 YYYY-MM-DD 星期X"""
    beijing = timezone(timedelta(hours=8))  # UTC+8 时区
    now = datetime.now(beijing)  # 获取东八区当前时间
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]  # 中文星期映射
    wd = weekdays[now.weekday()]  # weekday() 返回 0=周一
    return now.strftime("%Y-%m-%d"), f"星期{wd}"  # 返回日期和星期


def clean_html(text):
    """去除 HTML 标签，保留纯文本"""
    if not text:  # 空值保护
        return ""
    text = re.sub(r"<[^>]+>", "", text)  # 移除所有 HTML 标签
    text = re.sub(r"\s+", " ", text)  # 合并多余空白字符
    return text.strip()  # 去除首尾空格


def title_fingerprint(title):
    """生成标题指纹，用于去重（提取关键字符的哈希，中英文兼容）"""
    if not title:  # 空标题保护
        return ""
    chinese = re.findall(r"[一-鿿]+", title)  # 提取所有中文字符
    if chinese:  # 有中文就用中文字符做指纹
        seed = "".join(chinese)[:6]  # 取前6个汉字作为指纹种子
    else:  # 纯英文标题，取前30个字符做指纹
        seed = re.sub(r"[^a-zA-Z0-9]", "", title)[:30].lower()  # 只留字母数字，小写化
    if not seed:  # 种子为空时直接用标题哈希
        seed = title[:30]
    return hashlib.md5(seed.encode()).hexdigest()  # MD5 哈希作为指纹


# ============================================================
# 新闻源抓取函数（每个函数独立，单个失败不影响其他）
# ============================================================

async def fetch_zhihu(client):
    """
    知乎热榜 - 筛选科技/AI 相关话题
    API 无需认证，返回 JSON
    """
    url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
    params = {"limit": 30}  # 取 30 条然后筛选
    try:
        resp = await client.get(url, params=params, timeout=15)  # 发送 GET 请求
        data = resp.json()  # 解析 JSON
        articles = []  # 存放筛选结果
        tech_keywords = [  # 科技相关关键词，匹配到任一个就保留
            "AI", "人工智能", "大模型", "GPT", "ChatGPT", "OpenAI", "谷歌", "微软",
            "苹果", "华为", "小米", "特斯拉", "芯片", "GPU", "科技", "互联网",
            "机器", "算法", "自动驾驶", "机器人", "手机", "App", "软件", "数据",
            "模型", "发布", "融资", "编程", "代码", "量子", "5G",
        ]
        for item in data.get("data", []):  # 遍历热榜条目
            target = item.get("target", {})  # 每条热榜的 target 字段包含详情
            title = target.get("title", "")  # 问题标题
            excerpt = target.get("excerpt", "")  # 摘要
            if not title:  # 跳过空标题
                continue
            # 判断标题是否包含科技关键词
            is_tech = any(kw in title for kw in tech_keywords)
            if is_tech:
                articles.append({
                    "title": clean_html(title),  # 清理后的标题
                    "summary": clean_html(excerpt)[:200] if excerpt else "",  # 摘要限 200 字
                    "source": "知乎热榜",  # 来源标记
                    "url": target.get("url", f"https://www.zhihu.com/question/{target.get('id', '')}"),  # 原文链接
                    "hotness": int(target.get("detail_text", "0").replace("万", "0000").replace("万", "").replace("热度", "").strip() or 0),  # 热度值
                })
        return articles  # 返回筛选后的文章列表
    except Exception as e:
        print(f"[知乎] 获取失败: {e}")  # 容错：打印错误但不中断整体流程
        return []  # 返回空列表，不影响其他源


async def fetch_36kr(client):
    """
    36氪热榜 - 科技创投新闻
    POST 请求，返回 JSON
    """
    url = "https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot"
    payload = {
        "partner_id": "web",  # 固定参数
        "timestamp": int(time.time() * 1000),  # 当前毫秒时间戳
        "param": {"siteId": 1, "platformId": 2},  # 站点和平台 ID
    }
    try:
        resp = await client.post(url, json=payload, timeout=15)  # POST JSON 请求
        data = resp.json()  # 解析响应
        articles = []
        hot_list = data.get("data", {}).get("hotRankList", [])  # 热榜列表
        for item in hot_list[:20]:  # 取前 20 条
            tmpl = item.get("templateMaterial", {})  # 文章数据所在字段
            title = tmpl.get("title", "")  # 文章标题
            if not title:  # 跳过空标题
                continue
            articles.append({
                "title": clean_html(title),  # 清理后的标题
                "summary": clean_html(tmpl.get("description", "") or tmpl.get("summary", ""))[:200],  # 摘要
                "source": "36氪",  # 来源标记
                "url": f"https://www.36kr.com/p/{item.get('itemId', '')}",  # 36氪文章链接格式
                "hotness": item.get("hot", 0) or item.get("readCount", 0) or 0,  # 热度值
            })
        return articles
    except Exception as e:
        print(f"[36氪] 获取失败: {e}")
        return []


async def fetch_jiqizhixin(client):
    """
    机器之心 RSS - AI 专业媒体
    解析 RSS/XML 格式
    """
    url = "https://jiqizhixin.com/rss"
    try:
        resp = await client.get(url, timeout=15)  # 获取 RSS XML
        feed = feedparser.parse(resp.text)  # 解析 RSS
        articles = []
        for entry in feed.entries[:15]:  # 取前 15 条
            title = entry.get("title", "")  # RSS 标题
            if not title:
                continue
            summary = entry.get("summary", "") or entry.get("description", "")  # RSS 摘要
            articles.append({
                "title": clean_html(title),
                "summary": clean_html(summary)[:200],
                "source": "机器之心",
                "url": entry.get("link", ""),  # RSS link 字段
                "hotness": 50,  # RSS 无热度值，给个默认中等值
            })
        return articles
    except Exception as e:
        print(f"[机器之心] 获取失败: {e}")
        return []


async def fetch_qbitai(client):
    """
    量子位 - AI 科技媒体
    通过官方 API 获取最新文章
    """
    url = "https://www.qbitai.com/api/v1/articles"
    params = {"page": 1, "page_size": 15}  # 分页参数
    try:
        resp = await client.get(url, params=params, timeout=15)  # GET 请求
        data = resp.json()  # 解析 JSON
        articles = []
        items = data.get("data", {}).get("list", data.get("data", []))  # 兼容不同 API 结构
        if isinstance(items, dict):  # 如果返回的是字典，取 values
            items = list(items.values())
        for item in items:  # 遍历文章列表
            if isinstance(item, dict):  # 确保每个条目是字典
                title = item.get("title", "")  # 文章标题
                if not title:
                    continue
                articles.append({
                    "title": clean_html(title),
                    "summary": clean_html(item.get("description", "") or item.get("excerpt", ""))[:200],
                    "source": "量子位",
                    "url": item.get("url", "") or f"https://www.qbitai.com/article/{item.get('id', '')}",
                    "hotness": item.get("views", 0) or item.get("read_count", 0) or 40,  # 阅读量
                })
        return articles
    except Exception as e:
        print(f"[量子位] 获取失败: {e}")
        return []


async def fetch_hackernews(client):
    """
    Hacker News - 硅谷科技圈热点，筛选 AI 相关
    官方 Firebase API，免费无限制
    策略：先获取 Top 50，筛选 AI 相关标题，再获取详情
    """
    top_url = "https://hacker-news.firebaseio.com/v0/topstories.json"  # HN 热门文章 ID 列表
    item_url = "https://hacker-news.firebaseio.com/v0/item/{}.json"  # 单条详情 URL 模板
    ai_keywords = [  # AI 相关英文关键词
        "ai", "llm", "gpt", "openai", "anthropic", "claude", "gemini",
        "model", "machine learning", "deep learning", "neural", "transformer",
        "chatgpt", "copilot", "agent", "robot", "nvidia", "cuda", "gpu",
        "diffusion", "stable diffusion", "midjourney", "sora", "generative",
        "rag", "fine-tun", "embedding", "vector", "langchain", "llama",
        "mistral", "deepseek", "quantum", "agi", "alignment", "safety",
    ]
    try:
        ids_resp = await client.get(top_url, timeout=15)  # 获取 Top 文章 ID 列表
        all_ids = ids_resp.json()[:50]  # 取前 50 个 ID
        articles = []
        for sid in all_ids:  # 逐个获取详情
            try:
                detail = await client.get(item_url.format(sid), timeout=10)  # 获取单条详情
                item = detail.json()
                title = item.get("title", "")  # 文章标题
                if not title:  # 跳过空标题
                    continue
                # 检查标题是否包含 AI 关键词（不区分大小写）
                title_lower = title.lower()  # 小写化便于匹配
                if not any(kw in title_lower for kw in ai_keywords):  # 不匹配 AI 关键词则跳过
                    continue
                articles.append({
                    "title": title,  # 保留英文原标题
                    "summary": (item.get("text", "") or "")[:300],  # 正文前 300 字符作为摘要
                    "source": "Hacker News",  # 来源标记
                    "url": item.get("url", "") or f"https://news.ycombinator.com/item?id={sid}",  # 优先外部链接
                    "hotness": item.get("score", 0) or 0,  # HN 的 score 即热度
                })
            except Exception:
                continue  # 单条获取失败不影响整体
        return articles
    except Exception as e:
        print(f"[Hacker News] 获取失败: {e}")
        return []


async def fetch_techcrunch(client):
    """
    TechCrunch AI 频道 RSS - 海外 AI 创投新闻
    RSS 格式，内容权威
    """
    url = "https://techcrunch.com/category/artificial-intelligence/feed/"
    try:
        resp = await client.get(url, timeout=20)  # TechCrunch 可能较慢，给 20 秒超时
        feed = feedparser.parse(resp.text)  # 解析 RSS
        articles = []
        for entry in feed.entries[:10]:  # 取前 10 条
            title = entry.get("title", "")  # RSS 标题
            if not title:
                continue
            summary = entry.get("summary", "") or entry.get("description", "")  # RSS 摘要
            articles.append({
                "title": clean_html(title),  # 清理 HTML 标签
                "summary": clean_html(summary)[:250],  # 摘要限 250 字符
                "source": "TechCrunch AI",  # 来源标记
                "url": entry.get("link", ""),  # 原文链接
                "hotness": 55,  # 给较高默认值，确保海外新闻不会全被挤掉
            })
        return articles
    except Exception as e:
        print(f"[TechCrunch] 获取失败: {e}")
        return []


async def fetch_arxiv(client):
    """
    ArXiv 最新 AI 论文 - 学术前沿
    官方 API，免费无限制，返回 Atom XML
    涵盖 cs.AI, cs.CL, cs.LG, cs.CV 四个 AI 核心领域
    """
    categories = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]  # 四个 AI 核心分类
    cat_query = "+OR+".join([f"cat:{c}" for c in categories])  # 拼接 OR 查询
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": cat_query,  # 分类查询
        "sortBy": "submittedDate",  # 按提交日期排序
        "sortOrder": "descending",  # 最新的在前
        "max_results": "15",  # 取 15 条
    }
    try:
        # ArXiv API 要求手动拼接 URL 参数
        query_str = "&".join([f"{k}={v}" for k, v in params.items()])  # 手动拼接查询字符串
        full_url = f"{url}?{query_str}"  # 完整请求地址
        resp = await client.get(full_url, timeout=20)  # ArXiv API 可能较慢
        feed = feedparser.parse(resp.text)  # 解析 Atom XML
        articles = []
        for entry in feed.entries[:12]:  # 取前 12 条
            title = entry.get("title", "").strip()  # ArXiv 标题（英文）
            if not title:  # 跳过空标题
                continue
            summary = entry.get("summary", "")  # ArXiv 摘要（即论文 abstract）
            # 获取 PDF 链接
            pdf_url = ""  # 初始化 PDF 链接
            for link in entry.get("links", []):  # 遍历所有链接
                if link.get("title") == "pdf":  # 找 PDF 下载链接
                    pdf_url = link.get("href", "")
                    break
            articles.append({
                "title": clean_html(title),  # 清理标题
                "summary": clean_html(summary)[:250],  # 摘要限 250 字符
                "source": f"ArXiv ({entry.get('arxiv_primary_category', {}).get('term', 'AI')})",  # 标注子分类
                "url": pdf_url or entry.get("id", entry.get("link", "")),  # 优先 PDF，其次详情页
                "hotness": 45,  # 论文给中等热度，确保出现在列表中
            })
        return articles
    except Exception as e:
        print(f"[ArXiv] 获取失败: {e}")
        return []


# ============================================================
# 新闻整合
# ============================================================

def merge_articles(all_articles):
    """
    合并、去重、排序所有来源的新闻
    去重策略：基于标题中文字符的 MD5 指纹
    排序策略：按热度从高到低
    """
    seen = set()  # 已见过的标题指纹集合
    merged = []  # 合并结果
    for article in all_articles:  # 遍历所有文章
        fp = title_fingerprint(article["title"])  # 生成标题指纹
        if not fp or fp in seen:  # 指纹为空或已存在，跳过
            continue
        seen.add(fp)  # 标记为已见
        merged.append(article)  # 加入合并列表
    merged.sort(key=lambda x: x["hotness"], reverse=True)  # 按热度降序排列
    return merged[:MAX_NEWS]  # 返回前 N 条


# ============================================================
# TTS 语音合成
# ============================================================

async def generate_tts(text, output_path):
    """
    使用 edge-tts 生成 mp3 语音文件
    text: 要朗读的文字
    output_path: 输出 mp3 文件路径
    """
    communicate = edge_tts.Communicate(text, TTS_VOICE)  # 创建 TTS 通信对象
    await communicate.save(str(output_path))  # 异步保存为 mp3 文件
    print(f"[TTS] 语音已生成: {output_path}")


def build_tts_text(date_str, weekday_str, articles):
    """
    构建 TTS 朗读文本，口语化自然
    """
    lines = [f"早上好！今天是{date_str}，{weekday_str}。"]  # 开场问候
    lines.append("以下是今日 AI 和科技热点新闻摘要，共{}条。".format(len(articles)))  # 告知条数
    for i, art in enumerate(articles, 1):  # 逐条拼接
        lines.append(f"第{i}条，来自{art['source']}。{art['title']}。")  # 标题 + 来源
        if art.get("summary"):  # 如果有摘要，追加朗读
            lines.append(art["summary"])
    lines.append("以上是今日早报全部内容，祝你一天顺利！")  # 结尾
    return "\n".join(lines)  # 用换行分隔，edge-tts 会根据标点自然停顿


# ============================================================
# Bark 推送
# ============================================================

async def send_bark(client, title, body, url=None):
    """
    通过 Bark API 发送推送通知到 iPhone
    title: 通知标题
    body: 通知正文
    url: 点击通知后跳转的链接（可选）
    返回 True/False 表示是否成功
    """
    # 构建 Bark API 请求参数
    params = {
        "title": title[:100],  # 标题限 100 字符
        "body": body[:4000],  # 正文限 4000 字符（Bark 限制）
        "group": BARK_GROUP,  # 通知分组，同类通知自动折叠
        "icon": BARK_ICON,  # 通知图标
        "sound": "birdsong",  # 通知提示音
    }
    if url:  # 如果有跳转链接，加入参数
        params["url"] = url
    try:
        resp = await client.post(BARK_BASE, data=params, timeout=15)  # POST 表单数据
        result = resp.json()  # Bark 返回 JSON
        if result.get("code") == 200:  # Bark API 成功返回码是 200
            print(f"[Bark] 推送成功: {title}")
            return True
        else:
            print(f"[Bark] 推送失败: {result}")
            return False
    except Exception as e:
        print(f"[Bark] 推送异常: {e}")
        return False


async def send_bark_chunked(client, title_prefix, full_text, mp3_url=None):
    """
    分段推送长文本（Bark 每条约 4000 字符限制）
    先将全文按合理长度切分，逐条推送
    最后单独推送一条语音入口
    """
    # 按 3500 字符切分（留余量给前后文）
    chunk_size = 3500
    lines = full_text.split("\n")  # 按行拆分
    chunks = []  # 存放切好的段
    current = ""  # 当前累积的段
    for line in lines:  # 逐行累积
        if len(current) + len(line) + 1 > chunk_size and current:  # 超出限度
            chunks.append(current)  # 保存当前段
            current = line  # 开始新段
        else:
            current = current + "\n" + line if current else line  # 继续累积
    if current:  # 保存最后一段
        chunks.append(current)

    for i, chunk in enumerate(chunks):  # 逐条推送
        if len(chunks) > 1:  # 多段时加编号
            title = f"{title_prefix} ({i+1}/{len(chunks)})"
        else:
            title = title_prefix
        await send_bark(client, title, chunk)  # 发送文字消息

    if mp3_url:  # 如果有语音链接，单独推送一条语音通知
        await send_bark(
            client,
            "🔊 AI早报语音播报",  # 语音通知标题
            "点击播放今日早报语音",  # 语音通知正文
            url=mp3_url,  # 点击跳转到 mp3
        )


# ============================================================
# 主流程
# ============================================================

async def main():
    """主函数：依次执行新闻抓取 → 整合 → TTS → 推送"""
    date_str, weekday_str = get_beijing_time()  # 获取北京时间
    print(f"[启动] AI 早报 {date_str} {weekday_str}")

    OUTPUT_DIR.mkdir(exist_ok=True)  # 确保输出目录存在
    mp3_path = OUTPUT_DIR / MP3_FILE  # mp3 文件路径

    # --- 第 1 步：并发抓取所有新闻源 ---
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        results = await asyncio.gather(  # asyncio.gather 并发执行所有抓取
            fetch_zhihu(client),  # 知乎热榜
            fetch_36kr(client),  # 36氪
            fetch_jiqizhixin(client),  # 机器之心
            fetch_qbitai(client),  # 量子位
            fetch_hackernews(client),  # Hacker News（海外 AI 热点）
            fetch_techcrunch(client),  # TechCrunch AI（海外 AI 创投）
            fetch_arxiv(client),  # ArXiv（AI 学术论文前沿）
        )

    # --- 第 2 步：合并去重 ---
    all_articles = []  # 合并所有源的文章
    for result in results:  # 遍历每个源的结果
        all_articles.extend(result)  # 拼接到总列表
    print(f"[采集] 共获取 {len(all_articles)} 条（去重前）")

    articles = merge_articles(all_articles)  # 去重 + 排序 + 截断
    print(f"[筛选] 去重后保留 {len(articles)} 条")

    if not articles:  # 如果一条新闻都没抓到，推送错误通知后退出
        async with httpx.AsyncClient(headers=HEADERS) as client:
            await send_bark(client, "AI 早报异常", "今日未获取到新闻，请检查新闻源是否正常。")
        return

    # --- 第 3 步：构建文字摘要 ---
    text_lines = [f"🤖 AI 早报 | {date_str} {weekday_str}", "=" * 30, ""]
    for i, art in enumerate(articles, 1):  # 逐条格式化
        text_lines.append(f"【{i}】{art['title']}")  # 标题
        text_lines.append(f"  来源：{art['source']}")  # 来源
        if art.get("summary"):  # 有摘要就显示
            text_lines.append(f"  {art['summary']}")
        text_lines.append(f"  🔗 {art['url']}")  # 原文链接
        text_lines.append("")
    full_text = "\n".join(text_lines)  # 拼接为完整字符串

    # --- 第 4 步：生成 TTS 语音 ---
    tts_text = build_tts_text(date_str, weekday_str, articles)  # 构建朗读文本
    try:
        await generate_tts(tts_text, mp3_path)  # 生成 mp3
        tts_success = True
    except Exception as e:
        print(f"[TTS] 生成失败: {e}")
        tts_success = False  # TTS 失败不影响文字推送

    # --- 第 5 步：推送 ---
    mp3_url = ""  # mp3 的公网地址
    if tts_success and PAGES_URL:  # 只有 TTS 成功且配置了 Pages URL 才推送语音
        mp3_url = f"{PAGES_URL.rstrip('/')}/{MP3_FILE}"

    async with httpx.AsyncClient(headers=HEADERS) as client:
        title_prefix = f"🤖 AI 早报 {date_str}"  # 推送标题前缀
        await send_bark_chunked(client, title_prefix, full_text, mp3_url)  # 分段推送
        print("[完成] 所有推送已发送")


if __name__ == "__main__":
    asyncio.run(main())  # 运行主函数
