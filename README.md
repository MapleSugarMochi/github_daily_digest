# GitHub Trending Daily Digest

每天自动抓取 GitHub Trending 前 5 个热门项目，使用 DeepSeek 生成中文技术摘要，并通过邮件发送到指定邮箱。

这个项目适合放在 GitHub Actions 上免费定时运行，不需要自建服务器。配置好 DeepSeek API Key 和 SMTP 邮箱后，它会每天自动把 GitHub 上值得关注的新项目整理成一封中文邮件。

## 功能特性

- 每天定时抓取 GitHub Trending Daily 前 5 个项目
- 提取项目名称、链接、简介、主要语言、总 star 数和当日热度
- 使用 DeepSeek Chat Completions API 生成中文摘要
- 默认模型为 `deepseek-v4-pro`
- 通过 SMTP 发送纯文本邮件
- 支持 GitHub Actions 定时运行和手动触发
- 密钥通过 GitHub Actions Secrets 管理，不写入仓库
- workflow 会先安装依赖、验证依赖导入、运行单元测试，再发送邮件
- 当单个项目的 DeepSeek 摘要失败时，邮件仍会发送，并在对应项目中保留失败原因和基础信息

## 工作流程

```text
GitHub Actions 定时或手动触发
        |
        v
安装 Python 依赖并运行测试
        |
        v
抓取 GitHub Trending Daily
        |
        v
解析前 5 个热门项目
        |
        v
调用 DeepSeek 生成中文摘要
        |
        v
通过 SMTP 发送每日邮件
```

默认定时任务为每天 UTC 00:00 运行，对应北京时间 08:00。GitHub Actions 的定时任务可能会有几分钟到几十分钟延迟，这是正常现象。

## 项目结构

```text
github_daily_digest/
  README.md
  requirements.txt
  .env.example
  src/
    main.py
  tests/
    test_main.py
  .github/
    workflows/
      daily.yml
```

## 快速开始

### 1. Fork 或克隆仓库

```bash
git clone https://github.com/MapleSugarMochi/github_daily_digest.git
cd github_daily_digest
```

### 2. 配置 GitHub Secrets

进入你的 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

添加以下必填 Secrets：

| Secret | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `SMTP_HOST` | SMTP 服务器地址，例如 `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 端口，通常为 `587` |
| `SMTP_USER` | SMTP 登录账号 |
| `SMTP_PASSWORD` | SMTP 密码、App Password 或授权码 |
| `MAIL_FROM` | 发件人邮箱 |
| `MAIL_TO` | 收件人邮箱 |

可选 Secrets：

| Secret | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | DeepSeek 模型名。脚本会自动转为小写，避免大小写导致 API 报错 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API Base URL |

### 3. 手动运行一次

推送代码后，在 GitHub 仓库页面进入：

```text
Actions -> Daily GitHub Trending Digest -> Run workflow
```

第一次建议手动运行，确认 workflow 成功并且邮箱能收到摘要邮件。之后 GitHub Actions 会按计划自动运行。

## 本地运行

本地运行适合调试抓取、摘要和邮件发送流程。请不要把真实 `.env` 文件提交到仓库。

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置环境变量

可以参考 `.env.example` 准备环境变量。

PowerShell 示例：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com"
$env:SMTP_HOST="smtp.example.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="你的邮箱账号"
$env:SMTP_PASSWORD="你的邮箱密码或授权码"
$env:MAIL_FROM="发件人邮箱"
$env:MAIL_TO="收件人邮箱"

python src/main.py
```

macOS / Linux 示例：

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
export DEEPSEEK_MODEL="deepseek-v4-pro"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USER="你的邮箱账号"
export SMTP_PASSWORD="你的邮箱密码或授权码"
export MAIL_FROM="发件人邮箱"
export MAIL_TO="收件人邮箱"

python src/main.py
```

## 测试

运行单元测试：

```bash
python -m unittest discover -s tests -v
```

验证运行时依赖可导入：

```bash
python -c "import requests, bs4, openai"
```

GitHub Actions 中也会执行这两步。只有依赖验证和单元测试通过后，workflow 才会继续发送邮件。

## 邮件内容

邮件会包含当天 GitHub Trending 前 5 个项目：

- 项目名称
- GitHub 链接
- 主要语言
- 总 star 数
- 当日热度
- DeepSeek 生成的中文摘要

如果某个项目的摘要生成失败，邮件仍会发送，并在对应项目下显示失败原因和项目原始简介。

## 安全说明

- 不要把真实 `.env` 文件提交到 GitHub
- `.env.example` 只保存变量模板，不包含真实密钥
- `.gitignore` 已忽略 `.env`、`.env.*`、虚拟环境和 Python 缓存
- GitHub Actions 中的密钥应通过 Secrets 配置
- 如果 API Key 曾经泄露，请在 DeepSeek 控制台立即轮换

## 常见问题

### DeepSeek 返回 `Insufficient Balance`

这表示 DeepSeek 账户余额或额度不足。请检查账户余额、套餐额度或计费状态。

当前脚本会捕获单个项目的摘要失败，并继续发送邮件。邮件中会显示失败原因和项目基础信息。

### DeepSeek 返回模型名错误

DeepSeek 当前支持的模型名示例为：

```text
deepseek-v4-pro
deepseek-v4-flash
```

如果你在 GitHub Secrets 中配置了 `DEEPSEEK_MODEL`，建议使用小写模型名。脚本也会对模型名做小写规范化。

### SMTP 登录失败

常见原因：

- 邮箱未开启 SMTP
- 使用了登录密码，而不是 App Password 或授权码
- `SMTP_HOST` 或 `SMTP_PORT` 配置错误
- 邮箱服务商拦截自动化登录

Gmail 通常需要使用 App Password。QQ 邮箱、163 邮箱等通常需要在邮箱设置中开启 SMTP 并生成授权码。

### GitHub Trending 解析失败

项目通过解析 GitHub Trending 页面 HTML 获取数据。如果 GitHub 页面结构变化，`src/main.py` 中的 CSS 选择器可能需要调整。

### 定时任务没有准点运行

GitHub Actions 的 `schedule` 不是严格实时任务，可能会延迟几分钟到几十分钟。需要立即验证时，可以使用 `workflow_dispatch` 手动运行。

## Roadmap

- 支持 HTML 邮件
- 支持按语言筛选项目
- 支持读取项目 README 后再生成摘要
- 支持把每日摘要保存到 `digests/` 目录
- 支持同时发送到多个收件人
- 支持失败通知邮件

## License

本项目暂未声明开源许可证。如需公开复用或协作，建议先添加合适的 License 文件。
