import sys
import types
import unittest
from unittest.mock import Mock, patch

from src import main


TRENDING_HTML = """
<html>
  <body>
    <article class="Box-row">
      <h2><a href="/owner/repo"> owner / repo </a></h2>
      <p>A useful open source project.</p>
      <span itemprop="programmingLanguage">Python</span>
      <a class="Link--muted" href="/owner/repo/stargazers">12,345</a>
      <a class="Link--muted" href="/owner/repo/forks">678</a>
      <span class="d-inline-block float-sm-right">123 stars today</span>
    </article>
    <article class="Box-row">
      <h2><a href="/another/tool"> another / tool </a></h2>
      <a class="Link--muted" href="/another/tool/stargazers">42</a>
    </article>
  </body>
</html>
"""


class FakeTag:
    def __init__(self, text):
        self.text = text

    def get_text(self, strip=False):
        return self.text.strip() if strip else self.text


class FakeArticle:
    def __init__(self, fields):
        self.fields = fields

    def select_one(self, selector):
        return self.fields.get(selector)

    def select(self, selector):
        return self.fields.get(selector, [])


class FakeBeautifulSoup:
    def __init__(self, html, parser):
        self.html = html
        self.parser = parser

    def select(self, selector):
        if selector != "article.Box-row":
            return []
        return [
            FakeArticle(
                {
                    "h2 a": FakeTag(" owner / repo "),
                    "p": FakeTag("A useful open source project."),
                    "[itemprop='programmingLanguage']": FakeTag("Python"),
                    "a.Link--muted": [FakeTag("12,345"), FakeTag("678")],
                    "span.d-inline-block.float-sm-right": FakeTag("123 stars today"),
                }
            ),
            FakeArticle(
                {
                    "h2 a": FakeTag(" another / tool "),
                    "a.Link--muted": [FakeTag("42")],
                }
            ),
        ]


class ImportTests(unittest.TestCase):
    def test_module_imports_successfully_before_runtime_dependencies_are_used(self):
        self.assertEqual(main.TOP_N, 5)
        self.assertEqual(main.DEFAULT_DEEPSEEK_MODEL, "deepseek-v4-pro")
        self.assertEqual(main.DEFAULT_DEEPSEEK_BASE_URL, "https://api.deepseek.com")


class FetchTrendingReposTests(unittest.TestCase):
    def test_fetches_top_repositories_from_github_trending_html(self):
        response = Mock()
        response.text = TRENDING_HTML
        response.raise_for_status = Mock()
        requests_module = types.SimpleNamespace(get=Mock(return_value=response))
        bs4_module = types.SimpleNamespace(BeautifulSoup=FakeBeautifulSoup)

        with patch.dict(
            sys.modules,
            {"requests": requests_module, "bs4": bs4_module},
        ):
            repos = main.fetch_trending_repos()

        self.assertEqual(
            repos,
            [
                {
                    "name": "owner/repo",
                    "url": "https://github.com/owner/repo",
                    "description": "A useful open source project.",
                    "language": "Python",
                    "total_stars": "12,345",
                    "today_stars": "123 stars today",
                },
                {
                    "name": "another/tool",
                    "url": "https://github.com/another/tool",
                    "description": "",
                    "language": "Unknown",
                    "total_stars": "42",
                    "today_stars": "",
                },
            ],
        )
        requests_module.get.assert_called_once_with(
            main.GITHUB_TRENDING_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; GitHubTrendingDigest/1.0)"},
            timeout=30,
        )
        response.raise_for_status.assert_called_once_with()


class SummarizeRepoTests(unittest.TestCase):
    @patch.dict("src.main.os.environ", {}, clear=True)
    def test_summarizes_repository_with_deepseek_defaults(self):
        client = Mock()
        completion = Mock()
        completion.choices = [Mock(message=Mock(content="  中文摘要  "))]
        client.chat.completions.create.return_value = completion
        repo = {
            "name": "owner/repo",
            "url": "https://github.com/owner/repo",
            "description": "A useful open source project.",
            "language": "Python",
            "total_stars": "12,345",
            "today_stars": "123 stars today",
        }

        summary = main.summarize_repo(client, repo)

        self.assertEqual(summary, "中文摘要")
        call_kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "deepseek-v4-pro")
        self.assertEqual(call_kwargs["temperature"], 0.3)
        self.assertIn("owner/repo", call_kwargs["messages"][1]["content"])
        self.assertIn("不要编造", call_kwargs["messages"][1]["content"])

    @patch.dict("src.main.os.environ", {"DEEPSEEK_MODEL": ""}, clear=True)
    def test_uses_default_deepseek_model_when_secret_is_blank(self):
        client = Mock()
        completion = Mock()
        completion.choices = [Mock(message=Mock(content="中文摘要"))]
        client.chat.completions.create.return_value = completion
        repo = {
            "name": "owner/repo",
            "url": "https://github.com/owner/repo",
            "description": "A useful open source project.",
            "language": "Python",
            "total_stars": "12,345",
            "today_stars": "123 stars today",
        }

        main.summarize_repo(client, repo)

        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["model"],
            "deepseek-v4-pro",
        )

    @patch.dict("src.main.os.environ", {"DEEPSEEK_MODEL": "DeepSeek-V4-Pro"}, clear=True)
    def test_normalizes_deepseek_model_secret_to_lowercase(self):
        client = Mock()
        completion = Mock()
        completion.choices = [Mock(message=Mock(content="中文摘要"))]
        client.chat.completions.create.return_value = completion
        repo = {
            "name": "owner/repo",
            "url": "https://github.com/owner/repo",
            "description": "A useful open source project.",
            "language": "Python",
            "total_stars": "12,345",
            "today_stars": "123 stars today",
        }

        main.summarize_repo(client, repo)

        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["model"],
            "deepseek-v4-pro",
        )


class BuildDeepseekClientTests(unittest.TestCase):
    @patch.dict(
        "src.main.os.environ",
        {"DEEPSEEK_API_KEY": "key", "DEEPSEEK_BASE_URL": ""},
        clear=True,
    )
    def test_uses_default_base_url_when_secret_is_blank(self):
        mock_openai = Mock()
        openai_module = types.SimpleNamespace(OpenAI=mock_openai)

        with patch.dict(sys.modules, {"openai": openai_module}):
            client = main.build_deepseek_client()

        self.assertEqual(client, mock_openai.return_value)
        mock_openai.assert_called_once_with(
            api_key="key",
            base_url="https://api.deepseek.com",
        )


class BuildEmailBodyTests(unittest.TestCase):
    def test_builds_plain_text_daily_digest_email(self):
        repos = [
            {
                "name": "owner/repo",
                "url": "https://github.com/owner/repo",
                "description": "A useful open source project.",
                "language": "Python",
                "total_stars": "12,345",
                "today_stars": "",
            }
        ]

        body = main.build_email_body(repos, ["这是中文摘要。"])

        self.assertIn("GitHub Trending 每日摘要", body)
        self.assertIn("今日最热门的前 1 个项目", body)
        self.assertIn("1. owner/repo", body)
        self.assertIn("链接：https://github.com/owner/repo", body)
        self.assertIn("今日热度：Unknown", body)
        self.assertIn("这是中文摘要。", body)


class ParseMailRecipientsTests(unittest.TestCase):
    def test_parses_newline_separated_mail_to_recipients(self):
        recipients = main.parse_mail_recipients(
            "alice@example.com\n bob@example.com \n\ncharlie@example.com"
        )

        self.assertEqual(
            recipients,
            ["alice@example.com", "bob@example.com", "charlie@example.com"],
        )


class GenerateSummariesTests(unittest.TestCase):
    def test_uses_fallback_summary_when_deepseek_call_fails(self):
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError("Insufficient Balance")
        repos = [
            {
                "name": "owner/repo",
                "url": "https://github.com/owner/repo",
                "description": "A useful open source project.",
                "language": "Python",
                "total_stars": "12,345",
                "today_stars": "123 stars today",
            }
        ]

        summaries = main.generate_summaries(client, repos)

        self.assertEqual(len(summaries), 1)
        self.assertIn("摘要生成失败", summaries[0])
        self.assertIn("Insufficient Balance", summaries[0])
        self.assertIn("A useful open source project.", summaries[0])


class SendEmailTests(unittest.TestCase):
    @patch("src.main.smtplib.SMTP")
    @patch.dict(
        "src.main.os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "sender@example.com",
            "SMTP_PASSWORD": "secret",
            "MAIL_FROM": "sender@example.com",
            "MAIL_TO": "receiver@example.com",
        },
        clear=True,
    )
    def test_sends_email_through_configured_smtp_server(self, mock_smtp):
        server = mock_smtp.return_value.__enter__.return_value

        main.send_email("Subject", "Body")

        mock_smtp.assert_called_once_with("smtp.example.com", 587)
        server.starttls.assert_called_once_with()
        server.login.assert_called_once_with("sender@example.com", "secret")
        sent_message = server.send_message.call_args.args[0]
        self.assertEqual(sent_message["From"], "sender@example.com")
        self.assertEqual(sent_message["To"], "receiver@example.com")
        self.assertEqual(sent_message["Subject"], "Subject")

    @patch("src.main.smtplib.SMTP")
    @patch.dict(
        "src.main.os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "sender@example.com",
            "SMTP_PASSWORD": "secret",
            "MAIL_FROM": "sender@example.com",
            "MAIL_TO": "alice@example.com\nbob@example.com\ncharlie@example.com",
        },
        clear=True,
    )
    def test_sends_email_to_multiple_newline_separated_recipients_without_exposing_them(
        self, mock_smtp
    ):
        server = mock_smtp.return_value.__enter__.return_value

        main.send_email("Subject", "Body")

        sent_message = server.send_message.call_args.args[0]
        self.assertEqual(sent_message["To"], "sender@example.com")
        self.assertEqual(
            server.send_message.call_args.kwargs["to_addrs"],
            ["alice@example.com", "bob@example.com", "charlie@example.com"],
        )


if __name__ == "__main__":
    unittest.main()
