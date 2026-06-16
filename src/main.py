import base64
import json
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
GITHUB_API_URL = "https://api.github.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
README_SUMMARY_MAX_CHARS = 1200


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
    repo_articles = soup.select("article.Box-row")

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


def summarize_readme(readme_text):
    plain_text = re.sub(r"`{1,3}[^`]*`{1,3}", " ", readme_text)
    plain_text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", plain_text)
    plain_text = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", plain_text)
    plain_text = re.sub(r"[#>*_\-|]+", " ", plain_text)
    plain_text = " ".join(plain_text.split())
    return plain_text[:README_SUMMARY_MAX_CHARS]


def decode_readme_content(encoded_content):
    normalized = "".join(encoded_content.split())
    return base64.b64decode(normalized).decode("utf-8", errors="replace")


def enrich_repo(repo, session):
    enriched = dict(repo)
    enriched.setdefault("topics", [])
    enriched.setdefault("readme_summary", "")

    headers = {"Accept": "application/vnd.github+json"}
    try:
        repo_response = session.get(
            f"{GITHUB_API_URL}/repos/{repo['name']}",
            headers=headers,
            timeout=30,
        )
        repo_response.raise_for_status()
        enriched["topics"] = repo_response.json().get("topics", [])
    except Exception:
        enriched["topics"] = []

    try:
        readme_response = session.get(
            f"{GITHUB_API_URL}/repos/{repo['name']}/readme",
            headers=headers,
            timeout=30,
        )
        readme_response.raise_for_status()
        readme_text = decode_readme_content(readme_response.json().get("content", ""))
        enriched["readme_summary"] = summarize_readme(readme_text)
    except Exception:
        enriched["readme_summary"] = ""

    return enriched


def enrich_repos(repos):
    import requests

    session = requests.Session()
    return [enrich_repo(repo, session) for repo in repos]


def parse_json_object(content):
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response.")
    return json.loads(match.group(0))


def classify_repo_relevance(client, repo):
    prompt = f"""
请判断下面这个 GitHub Trending 项目是否与 AI / Agent / LLM / 大模型 / 智能体 / RAG / 多模态 / 生成式 AI / AI 开发工具链相关。

判断要求：
1. 只要项目明显属于上述领域，或主要服务于上述领域，就判定为相关。
2. 对 AI agent、AI agents、agent workflow、agent skills、computer-use agents 等自然语言表述要判定为相关。
3. 普通开发工具、框架、数据库、系统工具如果没有明显 AI/Agent 关系，应判定为不相关。
4. 信息不足时谨慎判断；不要因为项目很热门就判定为相关。
5. 只输出 JSON，不要输出 Markdown 或解释性文字。

输出格式：
{{"relevant": true, "reason": "一句话说明原因"}}

项目信息：
- 名称：{repo["name"]}
- 链接：{repo.get("url", "Unknown")}
- 描述：{repo.get("description", "")}
- 主要语言：{repo.get("language", "Unknown")}
- 总 star 数：{repo.get("total_stars", "Unknown")}
- 今日新增 star：{repo.get("today_stars", "")}
- Topics：{", ".join(repo.get("topics", [])) or "Unknown"}
- README 摘要：{repo.get("readme_summary", "") or "Unknown"}
"""

    try:
        completion = client.chat.completions.create(
            model=get_deepseek_model(),
            messages=[
                {
                    "role": "system",
                    "content": "你是一个严格但不过度保守的开源项目分类助手。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        result = parse_json_object(completion.choices[0].message.content)
        return {
            "relevant": bool(result.get("relevant")),
            "reason": str(result.get("reason", "")).strip() or "No reason provided.",
        }
    except Exception as error:
        return {"relevant": False, "reason": f"分类失败：{error}"}


def filter_ai_repos(client, repos):
    matches = []
    for repo in repos:
        classification = classify_repo_relevance(client, repo)
        repo["classification_reason"] = classification["reason"]
        if classification["relevant"]:
            matches.append(repo)
    return matches


def get_repo_short_name(repo_name):
    return repo_name.split("/")[-1]


def summarize_repo(client, repo):
    repo_short_name = get_repo_short_name(repo["name"])
    prompt = f"""
请用中文总结下面这个 GitHub 热门项目。

要求：
1. 直接输出正文，不要标题、列表或项目符号。
2. 第一句话必须以“**{repo_short_name}** 是一个”开头。
3. 用 3-5 句话说明它是做什么的，以及为什么可能值得关注。
4. 如果信息不足，请基于已有信息谨慎总结，不要编造。
5. 输出风格适合放在每日技术邮件里。

项目信息：
- 名称：{repo["name"]}
- 链接：{repo["url"]}
- 描述：{repo["description"]}
- 主要语言：{repo["language"]}
- 总 star 数：{repo["total_stars"]}
- 今日新增 star：{repo["today_stars"]}
- Topics：{", ".join(repo.get("topics", [])) or "Unknown"}
- README 摘要：{repo.get("readme_summary", "") or "Unknown"}
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


def split_repo_name(repo_name):
    if "/" not in repo_name:
        return repo_name, ""
    owner, repository = repo_name.split("/", 1)
    return owner, repository


def format_repo_display_name(repo_name):
    owner, repository = split_repo_name(repo_name)
    return f"{owner} /{repository}" if repository else owner


def format_repo_link(repo_name):
    owner, repository = split_repo_name(repo_name)
    if not repository:
        return f"https://github.com/{owner}"
    owner_url = f"https://github.com/{owner}"
    return f"[{owner_url}]({owner_url}) /{repository}"


def build_email_body(repos, summaries):
    lines = [
        "GitHub Trending AI 每日摘要",
        "",
        f"项目数：{len(repos)}",
        "",
    ]

    if not repos:
        lines.extend(
            [
                "今天没有发现 LLM 判定相关的 GitHub Trending 项目。",
                "",
            ]
        )
        return "\n".join(lines)

    for index, repo in enumerate(repos, start=1):
        lines.extend(
            [
                f"{index}. {format_repo_display_name(repo['name'])}",
                f"链接：{format_repo_link(repo['name'])}",
                f"语言：{repo['language']}",
                f"Stars：{repo['total_stars']}",
                "",
                f"筛选理由：{repo.get('classification_reason', 'Unknown')}",
                "",
                summaries[index - 1],
                "",
                "-" * 60,
                "",
            ]
        )

    return "\n".join(lines)


def parse_mail_recipients(value):
    return [recipient.strip() for recipient in value.splitlines() if recipient.strip()]


def send_email(subject, body):
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    mail_from = os.environ["MAIL_FROM"]
    mail_to = parse_mail_recipients(os.environ["MAIL_TO"])
    if not mail_to:
        raise RuntimeError("MAIL_TO must contain at least one recipient.")

    message = MIMEMultipart()
    message["From"] = mail_from
    message["To"] = mail_to[0] if len(mail_to) == 1 else mail_from
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message, to_addrs=mail_to)


def main():
    repos = fetch_trending_repos()
    if not repos:
        raise RuntimeError("No trending repositories found.")

    client = build_deepseek_client()
    repos = filter_ai_repos(client, enrich_repos(repos))

    summaries = generate_summaries(client, repos)
    body = build_email_body(repos, summaries)
    send_email("GitHub Trending AI 每日摘要", body)


if __name__ == "__main__":
    main()
