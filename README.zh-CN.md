# OOMOL Hermes Agent

[English](README.md)

一个开箱即用的
[Hermes Agent](https://github.com/NousResearch/hermes-agent) Docker 发行版，
预装 OO CLI、OOMOL Provider 和精选 Skills。

> 不想自行维护 Docker 环境？可以直接使用
> [OOMOL 托管的 Leina](https://app.oomol.com/)。

## 内置能力

- **OO CLI**：已经安装在镜像中，Hermes 可以在运行时直接使用。
- **OOMOL LLM**：直接将 OOMOL 托管的语言模型用作 Hermes Model Provider。
- **图片生成**：预配置 GPT Image 2 和 Nano Banana。
- **视频生成**：预配置 Seedance，支持文生视频和图生视频。
- **网页搜索**：使用 Jina Reader 作为 Hermes 默认搜索后端。
- **精选 Skills**：覆盖文档处理、公开内容研究、图表、任务规划和 Skill 管理。

## 快速开始

启动前：

1. 前往 [OOMOL Console](https://console.oomol.com/) 注册或登录账号。
2. [创建个人 API Key](https://console.oomol.com/api-key)。
3. 安装 Docker 和 Docker Compose。

创建环境变量文件：

```sh
cp .env.example .env
chmod 600 .env
```

在 `.env` 中填写 OOMOL API Key：

```dotenv
OO_API_KEY=your-oomol-api-key
```

OOMOL LLM 的地址、模型和 API 模式已经预填：

```dotenv
OO_LLM_BASE_URL=https://llm.oomol.com/v1
OO_LLM_MODEL=deepseek-v4-flash
OO_LLM_API_MODE=codex_responses
```

保留 `OO_LLM_MODEL` 即可使用预配置的 OOMOL 模型。如果不配置，则需要进入
Docker 自行配置要使用的模型。

使用项目提供的 [compose.yaml](compose.yaml) 拉取发布镜像并启动 Agent。消息平台
配置为可选步骤：

```sh
docker compose pull

# 可选：通过交互式向导配置消息平台
# 配置结果会保存在持久化数据卷中。如果已经配置过消息平台，可以跳过这条命令。
# 支持的平台及其配置要求：https://hermes-agent.nousresearch.com/docs/user-guide/messaging/
docker compose run --rm hermes hermes gateway setup

docker compose up -d
docker compose logs -f hermes
```

## 内置 Skills

镜像中包含精选的 Hermes、OOMOL 和 OO Framework Skills。

| 分类 | Skills |
| --- | --- |
| OO 托管能力 | `oo` |
| Skill 管理 | `oo-find-skills`、`oo-create-skill`、`oo-publish-skill` |
| Office 和 PDF | `office-files`、`pdf-files`、`nano-pdf`、`ocr-and-documents` |
| 公开内容研究 | `public-social-research` |
| 图表 | `architecture-diagram`、`excalidraw` |
| 任务规划 | `plan` |
| Hermes 使用指南 | `hermes-agent` |

通过这些 Skills，Hermes 可以处理 Office 和 PDF 文件、执行 OCR、研究公开社交
平台内容、创建图表、规划复杂任务，以及通过 OO 查找和管理其他 Skills。

## 配置与数据

更多配置见 [.env.example](.env.example)，包括镜像和 OOMOL 模型配置。

Hermes 配置、会话、OO CLI 状态和工作目录文件都保存在 Docker Compose 管理的
`hermes-data` Volume 中。`docker compose down` 会保留数据，
`docker compose down -v` 会删除 Volume。启动时还会把运行时 API Key 保存成
oo-cli 登录状态，让消息会话中的内置 OO Skills 可以正常使用。

请勿提交包含真实凭据的 `.env`，其中包含 OOMOL API Key。

## 关于本项目

本项目将指定版本的 Hermes Agent、OO CLI、精选 Skills 和 OOMOL Provider
Plugins 组装为 Docker 发行版，不是 Hermes Agent 的独立 Fork。

## 开发

```sh
make test
make build
make compose-up
```

开发 Compose 只运行消息 Gateway，不对宿主机开放端口。测试时请使用已经配置的
消息平台。

详细说明见 [docs/development.md](docs/development.md) 和
[docs/architecture.md](docs/architecture.md)。

## 许可证

本项目特有的发行版代码采用 MIT License。Hermes Agent 和第三方组件保留各自的
许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
