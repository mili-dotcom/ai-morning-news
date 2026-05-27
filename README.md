# AI 早报自动推送系统

每天早上 7:00 自动抓取全球 AI+科技热点新闻，中英双语对照 + TTS 语音播报，通过 Bark 推送到 iPhone。零操作、全免费。

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [新闻源说明](#3-新闻源说明)
4. [技术栈](#4-技术栈)
5. [代码逐模块解析](#5-代码逐模块解析)
6. [部署步骤](#6-部署步骤)
7. [日常使用](#7-日常使用)
8. [维护与排错](#8-维护与排错)

---

## 1. 项目概述

### 1.1 解决了什么问题

每天早上想了解 AI 行业动态，但要打开 5-10 个 App/网站一个个刷，费时间。这个系统自动帮你完成"信息收集 → 筛选 → 翻译 → 朗读 → 推送"的全流程，你只需要看一眼手机通知栏。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| 多源聚合 | 同时抓取 7 个新闻源（国内 4 个 + 国外 3 个） |
| 智能筛选 | 追踪 60+ 中美 AI 公司的关键词，自动过滤无关内容 |
| 中英双语 | 英文新闻自动翻译为中文，中英对照显示，方便学英语 |
| 语音播报 | 用 edge-tts 合成自然中文女声，点击通知即可播放 |
| 全自动 | GitHub Actions 每天早上 7:00 准时执行，无需任何操作 |

---

## 2. 系统架构

```
iPhone 通知栏
    ↑ (Bark API 推送)
    │
┌──────────────────────────┐
│       GitHub Actions      │  每天早上 7:00 (北京时间)
│   ┌──────────────────┐    │  UTC 23:00 = cron "0 23 * * *"
│   │     main.py       │    │
│   │                   │    │
│   │ ① 并发抓取 7 个源  │    │
│   │ ② 关键词过滤      │    │
│   │ ③ 去重 + 热度排序  │    │
│   │ ④ 英文→中文翻译   │    │
│   │ ⑤ edge-tts 生成mp3│    │
│   │ ⑥ Bark 推送通知   │    │
│   │ ⑦ mp3 发布 CDN    │    │
│   └──────────────────┘    │
└──────────────────────────┘
    ↑
    │ 抓取
    ▼
┌──────────────────────────────┐
│          7 个新闻源           │
│  知乎 │ 36氪 │ 机器之心 │ 量子位│
│  Hacker News │ TechCrunch │ ArXiv │
└──────────────────────────────┘
```

### 流程详解

1. **GitHub Actions 定时触发**：每天 UTC 23:00（北京时间 7:00），GitHub 服务器自动启动运行环境
2. **并发抓取**：Python `asyncio.gather()` 同时请求 7 个新闻源，总耗时约 3-5 秒（逐个请求需要 20-30 秒）
3. **关键词过滤**：每条新闻的标题+摘要必须命中 `AI_COMPANY_KEYWORDS` 列表中的至少一个词才保留
4. **去重排序**：基于标题中文字符的 MD5 指纹去重，按热度从高到低排列，取前 15 条
5. **翻译**：检测不含中文的文章，通过 Google 翻译 API 转为中文，实现中英对照
6. **TTS 合成**：将新闻拼接成口语化文本，用微软 Edge TTS 合成 mp3 语音
7. **Bark 推送**：分两条推送——文字版（长文本分段）+ 语音版（点击播放 mp3）
8. **CDN 发布**：mp3 推送到 gh-pages 分支，通过 jsDelivr CDN 提供全球加速访问

---

## 3. 新闻源说明

### 3.1 国内源（中文）

| 来源 | 类型 | 抓取方式 | 内容特点 |
|------|------|----------|----------|
| **知乎热榜** | API (公开) | `zhihu.com/api/v3/feed/topstory/hot-lists` | 实时热点，标题命中 AI 关键词则保留 |
| **36氪** | API (POST) | `gateway.36kr.com/api/mis/nav/home/nav/rank/hot` | 科技创投，取热榜前 20 条 |
| **机器之心** | RSS | `jiqizhixin.com/rss` | AI 专业媒体，取最新 15 篇 |
| **量子位** | API | `qbitai.com/api/v1/articles` | AI 科技媒体，按阅读量排序 |

### 3.2 国外源（英文）

| 来源 | 类型 | 抓取方式 | 内容特点 |
|------|------|----------|----------|
| **Hacker News** | Firebase API | `hacker-news.firebaseio.com/v0/` | 硅谷科技圈热点，从 Top 50 筛选 AI 相关 |
| **TechCrunch AI** | RSS | `techcrunch.com/category/artificial-intelligence/feed/` | 海外 AI 创投新闻 |
| **ArXiv** | Atom API | `export.arxiv.org/api/query` | AI 学术论文前沿（cs.AI/CL/LG/CV） |

### 3.3 追踪的 AI 公司（60+）

所有新闻源的标题和摘要都会用以下关键词列表做匹配，确保不遗漏：

```
美国大厂：OpenAI, DeepMind, Anthropic, Google AI, Meta AI, Apple AI, Microsoft AI
美国芯片：NVIDIA, AMD, Intel, Groq, Cerebras
美国创业：xAI, Perplexity, Midjourney, Stability AI, Cohere, Scale AI
自动驾驶：Tesla(Optimus/FSD), Waymo, Figure AI, Boston Dynamics
中国大厂：百度文心, 阿里通义, 腾讯混元, 字节豆包, 华为盘古
大模型：智谱, Kimi月之暗面, MiniMax, 百川, 零一万物, 阶跃星辰
DeepSeek, 商汤, 旷视, 云从, 依图
中国芯片：寒武纪, 地平线, 壁仞, 摩尔线程, 海光
自动驾驶：小马智行, 文远知行, Momenta, 元戎启行
```

---

## 4. 技术栈

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| **语言** | Python 3.11+ | 异步友好，爬虫/数据处理生态成熟 |
| **HTTP 客户端** | `httpx` (异步) | 比 requests 快 3-5 倍（并发场景） |
| **RSS 解析** | `feedparser` | 标准库级别稳定，支持 Atom/RSS |
| **TTS 语音** | `edge-tts` | 微软免费，中文女声极其自然 |
| **翻译** | `deep-translator` | 封装 Google 翻译，免费 |
| **推送** | Bark App | 开源免费，iPhone 原生通知 |
| **调度** | GitHub Actions | 免费，每天 ~3 分钟用量 |
| **CDN** | jsDelivr | 免费，国内可访问 |

### 为什么不用传统服务器

| 传统方式 | GitHub Actions |
|----------|---------------|
| 需要租服务器（50-200 元/月） | 完全免费（公开仓库无限用） |
| 需要维护操作系统 | GitHub 维护运行环境 |
| 需要配置进程守护 | cron 表达式搞定 |
| 出问题需要登录服务器看日志 | 网页直接查看运行日志 |

---

## 5. 代码逐模块解析

### 5.1 文件结构

```
ai-morning-news/
├── main.py                    # 主脚本（所有逻辑）
├── requirements.txt           # Python 依赖
├── .gitignore                 # Git 忽略规则
├── README.md                  # 本文档
└── .github/
    └── workflows/
        └── daily-news.yml     # GitHub Actions 工作流定义
```

### 5.2 main.py 核心模块

#### 配置区（第 22-85 行）

```python
BARK_KEY = os.environ.get("BARK_KEY", "...")   # 从 GitHub Secrets 读取推送密钥
MAX_NEWS = 15                                    # 每天最多推送 15 条
TTS_VOICE = "zh-CN-XiaoxiaoNeural"              # 中文女声
AI_COMPANY_KEYWORDS = [...]                      # 60+ 公司关键词黑名单
```

**含义**：把可变配置集中在顶部，方便修改。`BARK_KEY` 走环境变量是为了不把密钥写死在代码里（防止泄露）。

#### 关键词过滤机制

```python
def title_fingerprint(title):
    chinese = re.findall(r"[一-鿿]+", title)    # 提取中文字符
    seed = "".join(chinese)[:6]                  # 取前 6 个作为指纹
    return hashlib.md5(seed.encode()).hexdigest() # MD5 哈希
```

**含义**：不同新闻源可能发同一件事但标题略有不同。用前 6 个中文字符的 MD5 作为"指纹"，指纹相同就是重复文章。

#### 并发抓取（asyncio.gather）

```python
results = await asyncio.gather(
    fetch_zhihu(client),          # 知乎
    fetch_36kr(client),           # 36氪
    fetch_jiqizhixin(client),     # 机器之心
    fetch_qbitai(client),         # 量子位
    fetch_hackernews(client),     # Hacker News
    fetch_techcrunch(client),     # TechCrunch
    fetch_arxiv(client),          # ArXiv
)
```

**含义**：7 个源同时请求，总耗时 = 最慢的那个源的时间（约 3-5 秒），而不是 7 个源逐个加起来（约 20-30 秒）。

#### 翻译流程

```python
async def translate_articles(articles):
    for art in articles:
        if not has_chinese(title + summary):     # 只翻译纯英文
            cn_title = await asyncio.to_thread(translate_text, title)   # 线程池翻译
            art["title_cn"] = cn_title
            art["summary_cn"] = cn_summary
```

**含义**：`asyncio.to_thread()` 是关键——翻译库是同步的（会阻塞事件循环），把它扔到线程池里跑，不耽误其他异步任务。

#### TTS 合成

```python
async def generate_tts(text, output_path):
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(str(output_path))
```

**含义**：`edge-tts` 是微软浏览器内置的 TTS 引擎，调用的是微软云端的语音合成 API，免费无限制。`zh-CN-XiaoxiaoNeural` 是最自然的中文女声。

#### Bark 分段推送

```python
async def send_bark_chunked(client, title_prefix, full_text, mp3_url=None):
    chunk_size = 3500
    # 按 3500 字符切分长文本
    for i, chunk in enumerate(chunks):
        await send_bark(client, f"{title_prefix} ({i+1}/{len(chunks)})", chunk)
    # 最后推送语音入口
    if mp3_url:
        await send_bark(client, "🔊 AI早报语音播报", "点击播放", url=mp3_url)
```

**含义**：Bark 单条推送限制约 4000 字符。15 条新闻的完整摘要可能超过这个限制，所以按 3500 字符分段，接收端会收到若干条连续通知。

### 5.3 GitHub Actions 工作流（daily-news.yml）

```yaml
on:
  schedule:
    - cron: "0 23 * * *"        # UTC 23:00 = 北京时间 7:00
  workflow_dispatch:              # 允许手动触发测试
```

**含义**：
- `cron "0 23 * * *"` 是 crontab 语法：分 时 日 月 周。
- GitHub Actions 跑的是 UTC 时间，北京时间 = UTC + 8，所以 UTC 23 点 = 北京次日 7 点。
- `workflow_dispatch` 让你可以在网页上点按钮手动触发（测试用）。

```yaml
- uses: peaceiris/actions-gh-pages@v3
  with:
    publish_dir: ./output
    publish_branch: gh-pages
```

**含义**：`peaceiris/actions-gh-pages` 是社区维护的 GitHub Actions 插件，把 `output/` 目录推送到 `gh-pages` 分支。jsDelivr CDN 从这个分支读取 `news.mp3` 提供给全局访问。

---

## 6. 部署步骤

### 第一步：准备工作（共 5 分钟）

1. **安装 Bark App**（App Store 搜索 "Bark"）
   - 打开 App → 复制你的推送 URL（格式：`https://api.day.app/xxxxxx/`）

2. **创建 GitHub 仓库**
   - 打开 github.com/new
   - 名称填 `ai-morning-news`
   - 勾选 **Public**（必须公开，jsDelivr CDN 要求）
   - 不要勾选 "Add a README file"
   - 点 Create repository

3. **克隆并配置**
   - 把代码推送到仓库
   - 在仓库 Settings → Secrets → Actions → 新建 `BARK_KEY`，值为你的 Bark URL 中的那串密钥

### 第二步：验证（等 3 分钟）

1. 打开仓库的 Actions 页面
2. 点击 "AI 早报推送" → "Run workflow" → 手动触发
3. 看手机是否收到 Bark 推送（文字 + 语音）

### 第三步：完成

从此每天早 7:00 自动推送，不需要再做任何操作。

---

## 7. 日常使用

### 你会收到什么

```
早上 7:00 手机通知栏弹出：

┌─────────────────────────────┐
│ 🤖 AI 早报 2026-05-28 (1/2) │
│                             │
│ 【1】NVIDIA Launches...     │
│      NVIDIA发布下代AI芯片    │
│   来源：TechCrunch AI        │
│   The new Blackwell...      │
│   新一代Blackwell芯片性能... │
│   🔗 https://...            │
│                             │
│ 【2】DeepSeek 开源新模型      │
│   ...                       │
└─────────────────────────────┘

┌─────────────────────────────┐
│ 🔊 AI早报语音播报            │
│ 点击播放今日早报语音          │
└─────────────────────────────┘
```

### 语音播报怎么听

- 点第二条通知 → 浏览器打开 → 自动播放 mp3
- 内容：`早上好！今天是 2026年5月28日，星期四。以下是今日 AI 和科技热点新闻摘要，共 15 条。第一条，来自 TechCrunch AI。NVIDIA发布下代AI芯片...`
- 全程约 2-3 分钟，适合通勤、刷牙、吃早餐时收听

---

## 8. 维护与排错

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 某天没收推送 | 某个新闻源 API 挂了导致脚本报错 | 去 Actions 页面看运行日志，定位哪个源出错 |
| 新闻太少 | 当天 AI 关键词命中率低 | 可以增加 `AI_COMPANY_KEYWORDS` 中的词汇 |
| TTS 语音不播放 | jsDelivr CDN 缓未更新 | 手动触发一次 workflow 强制刷新 |
| 推送内容消失 | Bark 通知分组自动折叠了 | 在 Bark App 中展开分组即可 |

### 如何查看运行日志

1. 打开 https://github.com/mili-dotcom/ai-morning-news/actions
2. 点击最近一次运行
3. 点 "generate-and-push" → 展开查看所有 `print()` 输出

### 如何添加新新闻源

在 `main.py` 中按模板添加一个新函数：

```python
async def fetch_xxx(client):
    """新新闻源"""
    try:
        # ... 抓取逻辑 ...
        return articles
    except Exception as e:
        print(f"[新源] 获取失败: {e}")
        return []
```

然后在 `main()` 的 `asyncio.gather()` 中加入 `fetch_xxx(client)`。

### 如何修改推送时间

修改 `.github/workflows/daily-news.yml` 中的 cron：

```yaml
- cron: "0 23 * * *"   # UTC 23:00
```

北京时间 = UTC + 8。例如想改到早 8:00，UTC = 0:00 → `cron: "0 0 * * *"`。

---

## 附录：项目中的关键设计决策

### 为什么不是 App 而是脚本

App 需要上架审核、维护前端、适配 iOS 版本、处理推送证书。脚本 + 通知栏 = 零维护成本 + 同等体验。

### 为什么用 GitHub Actions 而不是自己租服务器

GitHub Actions 对公开仓库完全免费，每天 3-5 分钟远低于 2000 分钟/月限额。而且 GitHub 的服务器在海外，访问 Hacker News、ArXiv 等国外源速度极快。

### 为什么关键词匹配而不是 AI 分类

用 AI 分类（如调用大模型 API 判断新闻是否相关）更"高级"，但也有代价：需要 API key（成本）、响应延迟（3-5 秒变成 15-20 秒）、偶尔误判。关键词匹配简单、可解释、零延迟，对这个场景来说足够好。
