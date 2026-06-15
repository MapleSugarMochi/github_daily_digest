# GitHub Trending Daily Digest

每天自动审阅 GitHub Trending 上最热门的前 5 个项目，调用 DeepSeek API 生成中文摘要，并通过邮件发送到指定邮箱。

这个项目适合用 GitHub Actions 免费定时运行，不需要自己购买服务器。

## 功能

- 每天定时抓取 GitHub Trending 前 5 个项目
- 提取项目名称、链接、描述、语言、star 数等信息
- 调用 DeepSeek API 生成中文总结
- 通过 SMTP 发送邮件
- 所有密钥通过 GitHub Secrets 管理

## 工作流程

```text
GitHub Actions 定时触发
        |
        v
Python 脚本抓取 GitHub Trending
        |
        v
筛选前 5 个热门项目
        |
        v
调用 DeepSeek API 生成中文摘要
        |
        v
通过 SMTP 发送每日邮件
```

## 推荐项目结构

```text
github-trending-digest/
  README.md
  requirements.txt
  src/
    main.py
  .github/
    workflows/
      daily.yml
```

## 第一步：创建项目文件

新建一个 GitHub 仓库，然后在仓库里创建下面几个文件。

### `requirements.txt`

```txt
beautifulsoup4==4.12.3
openai==1.59.7
requests==2.32.3
```

### `src/main.py`

```python
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup
from openai import OpenAI


GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
TOP_N = 5


def fetch_trending_repos():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; GitHubTrendingDigest/1.0)"
    }
    response = requests.get(GITHUB_TRENDING_URL, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    repo_articles = soup.select("article.Box-row")[:TOP_N]

    repos = []
    for article in repo_articles:
        title_tag = article.select_one("h2 a")
        if not title_tag:
            continue

        repo_path = " ".join(title_tag.get_text(strip=True).split())
        repo_path = repo_path.replace(" / ", "/")
        repo_url = f"https://github.com/{repo_path}"

        description_tag = article.select_one("p")
        description = description_tag.get_text(strip=True) if description_tag else ""

        language_tag = article.select_one("[itemprop='programmingLanguage']")
        language = language_tag.get_text(strip=True) if language_tag else "Unknown"

        star_tags = article.select("a.Link--muted")
        total_stars = star_tags[0].get_text(strip=True) if star_tags else "Unknown"

        today_stars_tag = article.select_one("span.d-inline-block.float-sm-right")
        today_stars = today_stars_tag.get_text(strip=True) if today_stars_tag else ""

        repos.append(
            {
                "name": repo_path,
                "url": repo_url,
                "description": description,
                "language": language,
                "total_stars": total_stars,
                "today_stars": today_stars,
            }
        )

    return repos


def summarize_repo(client, repo):
    prompt = f"""
请用中文总结下面这个 GitHub 热门项目。

要求：
1. 用 3-5 句话说明它是做什么的。
2. 说明它为什么可能值得关注。
3. 如果信息不足，请基于已有信息谨慎总结，不要编造。
4. 输出风格适合放在每日技术邮件里。

项目信息：
- 名称：{repo["name"]}
- 链接：{repo["url"]}
- 描述：{repo["description"]}
- 主要语言：{repo["language"]}
- 总 star 数：{repo["total_stars"]}
- 今日新增 star：{repo["today_stars"]}
"""

    completion = client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        messages=[
            {
                "role": "system",
                "content": "你是一个专业的软件工程和开源项目分析助手。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    return completion.choices[0].message.content.strip()


def build_email_body(repos, summaries):
    lines = [
        "GitHub Trending 每日摘要",
        "",
        f"今日最热门的前 {len(repos)} 个项目：",
        "",
    ]

    for index, repo in enumerate(repos, start=1):
        lines.extend(
            [
                f"{index}. {repo['name']}",
                f"链接：{repo['url']}",
                f"语言：{repo['language']}",
                f"Stars：{repo['total_stars']}",
                f"今日热度：{repo['today_stars'] or 'Unknown'}",
                "",
                summaries[index - 1],
                "",
                "-" * 60,
                "",
            ]
        )

    return "\n".join(lines)


def send_email(subject, body):
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    mail_from = os.environ["MAIL_FROM"]
    mail_to = os.environ["MAIL_TO"]

    message = MIMEMultipart()
    message["From"] = mail_from
    message["To"] = mail_to
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)


def main():
    repos = fetch_trending_repos()
    if not repos:
        raise RuntimeError("No trending repositories found.")

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )

    summaries = [summarize_repo(client, repo) for repo in repos]
    body = build_email_body(repos, summaries)
    send_email("GitHub Trending 每日摘要", body)


if __name__ == "__main__":
    main()
```

### `.github/workflows/daily.yml`

```yaml
name: Daily GitHub Trending Digest

on:
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:

jobs:
  send-digest:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Send digest email
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          DEEPSEEK_MODEL: ${{ secrets.DEEPSEEK_MODEL || 'deepseek-v4-pro' }}
          DEEPSEEK_BASE_URL: ${{ secrets.DEEPSEEK_BASE_URL }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          MAIL_FROM: ${{ secrets.MAIL_FROM }}
          MAIL_TO: ${{ secrets.MAIL_TO }}
        run: python src/main.py
```

`cron: "0 0 * * *"` 表示每天 UTC 00:00 运行一次。北京时间是 UTC+8，所以对应北京时间早上 08:00。

如果你想改成北京时间每天早上 09:00 发送，需要设置为：

```yaml
cron: "0 1 * * *"
```

## 第二步：准备 DeepSeek API Key

1. 打开 DeepSeek 开放平台。
2. 创建 API Key。
3. 复制 API Key，稍后填入 GitHub Secrets。

脚本默认使用：

```text
deepseek-v4-pro
```

如果你想以后换模型，可以在 GitHub Secrets 里添加：

```text
DEEPSEEK_MODEL
```

例如：

```text
deepseek-v4-pro
```

## 第三步：准备邮箱 SMTP

你需要一个支持 SMTP 的邮箱服务。常见选择：

- Gmail
- Outlook
- QQ 邮箱
- 163 邮箱
- 企业邮箱
- SendGrid
- Resend

不同邮箱的 SMTP 配置不同。下面是常见示例。

### Gmail 示例

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=你的 Gmail 地址
SMTP_PASSWORD=你的 Gmail App Password
MAIL_FROM=你的 Gmail 地址
MAIL_TO=接收摘要的邮箱地址
```

Gmail 通常不能直接使用登录密码，需要使用 App Password。

### QQ 邮箱示例

```text
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=你的 QQ 邮箱
SMTP_PASSWORD=QQ 邮箱 SMTP 授权码
MAIL_FROM=你的 QQ 邮箱
MAIL_TO=接收摘要的邮箱地址
```

QQ 邮箱通常需要在邮箱设置里开启 SMTP，并生成授权码。

## 第四步：配置 GitHub Secrets

进入你的 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

添加下面这些 Secrets：

```text
DEEPSEEK_API_KEY
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
MAIL_FROM
MAIL_TO
```

可选 Secrets：

```text
DEEPSEEK_MODEL
DEEPSEEK_BASE_URL
```

如果不设置可选项，脚本会默认使用：

```text
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## 第五步：本地测试

如果你想先在本地测试，可以在本机设置环境变量后运行：

```bash
pip install -r requirements.txt
python src/main.py
```

macOS / Linux 可以这样设置环境变量：

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USER="你的邮箱账号"
export SMTP_PASSWORD="你的邮箱密码或授权码"
export MAIL_FROM="发件人邮箱"
export MAIL_TO="收件人邮箱"

python src/main.py
```

Windows PowerShell 可以这样设置：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:SMTP_HOST="smtp.example.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="你的邮箱账号"
$env:SMTP_PASSWORD="你的邮箱密码或授权码"
$env:MAIL_FROM="发件人邮箱"
$env:MAIL_TO="收件人邮箱"

python src/main.py
```

## 第六步：手动触发一次

代码推送到 GitHub 后，进入仓库页面：

```text
Actions -> Daily GitHub Trending Digest -> Run workflow
```

第一次建议手动运行一次，确认邮件能正常收到。

## 注意事项

### GitHub Trending 页面结构可能变化

这个方案通过解析 GitHub Trending 页面获取热门项目。如果 GitHub 页面结构变化，`fetch_trending_repos()` 里的 CSS 选择器可能需要调整。

### GitHub Actions 的定时时间不是严格实时

GitHub Actions 的 `schedule` 任务可能会有几分钟到几十分钟延迟，这是正常现象。

### SMTP 登录失败

如果邮件发送失败，通常是下面几个原因：

- 邮箱没有开启 SMTP
- 使用了登录密码，而不是邮箱授权码
- `SMTP_HOST` 或 `SMTP_PORT` 配置错误
- 邮箱服务商拦截了自动化登录

### DeepSeek 调用失败

如果 DeepSeek API 调用失败，检查：

- `DEEPSEEK_API_KEY` 是否正确
- 账户是否有余额或可用额度
- `DEEPSEEK_BASE_URL` 是否设置正确
- 模型名是否正确

## 可以继续增强的方向

- 把邮件改成 HTML 格式
- 加入项目 README 内容后再总结
- 支持按语言筛选，比如只看 Python、TypeScript、AI 项目
- 把每日摘要保存到仓库的 `digests/` 目录
- 失败时发送错误通知
- 支持同时发送到多个邮箱

## 最小可用版本

只要你完成下面四件事，这个项目就可以跑起来：

1. 创建 `requirements.txt`
2. 创建 `src/main.py`
3. 创建 `.github/workflows/daily.yml`
4. 在 GitHub Secrets 里配置 DeepSeek 和 SMTP 信息

完成后，GitHub Actions 会每天自动运行，并把 GitHub Trending 前 5 个项目摘要发送到你的邮箱。


