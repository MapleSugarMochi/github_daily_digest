import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
TOP_N = 5
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def get_env_or_default(name, default):
    return os.getenv(name) or default


def get_deepseek_model():
    return get_env_or_default("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip().lower()


def fetch_trending_repos():
    import requests
    from bs4 import BeautifulSoup

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
        model=get_deepseek_model(),
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


def build_fallback_summary(repo, error):
    description = repo["description"] or "该项目没有提供简介。"
    return (
        "摘要生成失败，已保留项目基础信息供参考。\n"
        f"失败原因：{error}\n"
        f"项目简介：{description}"
    )


def generate_summaries(client, repos):
    summaries = []
    for repo in repos:
        try:
            summaries.append(summarize_repo(client, repo))
        except Exception as error:
            summaries.append(build_fallback_summary(repo, error))
    return summaries


def build_deepseek_client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=get_env_or_default("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
    )


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

    client = build_deepseek_client()

    summaries = generate_summaries(client, repos)
    body = build_email_body(repos, summaries)
    send_email("GitHub Trending 每日摘要", body)


if __name__ == "__main__":
    main()
