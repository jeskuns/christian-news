# 基督教世界新闻 · Christian News

每日自动采集全球基督教资讯源，生成静态知识库网站。
仿照 `company/power-tools-kb` 架构（多源采集 → 解析 → 建库 → 静态站点生成 → 定时调度）。

## 分类

| 分类 key | 说明 | 图标 |
|---|---|---|
| `news` | 基督教世界资讯 | 📰 |
| `persecution` | 信仰自由与逼迫 | 🕊 |
| `mission` | 宣教运动 | 🌍 |
| `church` | 教会与机构 | ⛪ |
| `theology` | 神学与合一 | 📖 |
| `heresy` | 异端辨析 | ⚠ |
| `culture` | 文化媒体 | 🎬 |
| `wiki` | 百科背景 | 📚 |

除主题分类外，首页侧栏还提供**热门地区 / 热门主题**两个维度（按标题+摘要+标签命中统计）。

## 项目结构

```
Christian-News/
├── config/
│   └── sources.yaml          # 信息源配置（RSS / Google News 关键词检索 / Wikipedia）
├── data/
│   ├── raw/                  # 每日原始采集数据（按日期归档）
│   └── db/                   # 按分类索引的数据库（articles.json + 各分类 json）
├── site/                     # 生成的静态网站
│   ├── index.html
│   ├── categories/
│   └── assets/
├── src/
│   ├── collector.py          # 多源并发采集引擎
│   ├── scheduler.py          # 每日定时调度
│   ├── models.py             # 数据模型（Article 含 region 地区维度）
│   ├── parsers/              # rss / generic / wikipedia / news_search
│   ├── generators/          # 静态站点生成器（Jinja2 模板）
│   ├── translator.py         # 英文标题自动译中（本地缓存）
│   └── utils.py
├── run.py                    # 命令行入口
├── update.bat                # Windows 一键更新脚本
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 基于已有数据库生成网站（离线，已内置示例数据）

```bash
python run.py generate
```

生成完成后打开 `site/index.html` 即可浏览（示例数据已随仓库提供）。

### 3. 立即执行一次采集并生成网站（需联网）

```bash
python run.py full --workers 8
```

### 4. 启动每日自动更新（默认每天 08:30 Asia/Hong_Kong）

```bash
python run.py schedule --hour 8 --minute 30
```

或双击 `update.bat` 手动执行一次（采集 + 生成 + 提交 GitHub 触发部署）。

## 常用命令

| 命令 | 说明 |
|------|------|
| `python run.py collect` | 仅采集并保存数据 |
| `python run.py generate` | 仅基于已有数据库生成网站 |
| `python run.py full` | 采集 + 生成 |
| `python run.py schedule` | 每日定时调度 |

## 数据源配置

所有信息源集中管理于 `config/sources.yaml`，每个源包含：

- `name`：来源名称
- `url`：采集地址
- `category`：所属分类
- `parser`：`rss` / `generic` / `wikipedia` / `news_search`
- `language` / `country`：语言与国家
- `region`：地区维度（可选，用于首页热门地区）
- `max_items`：每次最大采集条目数
- `extra.query`（news_search 用）：检索关键词

## 部署（Cloudflare Pages）

推送即自动部署，并每天自动采集更新（GitHub Actions → `wrangler pages deploy` 上传 `site/`）：

- 部署目录：`site/`
- 项目名：`christian-news`（见 `wrangler.toml`）
- 仓库 Secrets：`CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`
- 工作流 `.github/workflows/deploy.yml`：
  - `schedule`：`cron: "0 0 * * *"`（UTC 00:00 = **北京时间每天 08:00**）自动采集并发布
  - `workflow_dispatch`：可手动触发
  - 流程：安装依赖 → `python run.py full` 采集+生成 → `wrangler pages deploy site` → 提交刷新后的 `site/`、`data/`
- 本地预览部署：`npx wrangler pages deploy site`

## 内容说明

本仓库内置的 `data/db/articles.json` 为**示意性示例数据**，用于离线预览站点结构；
实际部署请运行 `python run.py full` 采集真实资讯，并遵守各来源版权与转载规范。
