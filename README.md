# Gemini Playwright Bot

这是一个 AI 驱动的聊天机器人，它使用 Google 的 Gemini 模型来理解自然语言指令，并通过 Playwright MCP 服务器来控制一个真实的浏览器，以完成网页自动化任务。

这个机器人可以：
-   导航到指定网页。
-   根据指令与页面元素交互（点击、输入等）。
-   获取页面内容并进行总结。
-   执行多步骤的复杂网页任务。

## 1. 环境准备 (Prerequisites)

在开始之前，请确保您的系统上已经安装了以下软件：

-   **Python 3.10+**
-   **Docker**: Docker Desktop (Windows/macOS) 或 Docker Engine (Linux)。请确保 Docker 服务正在运行。
-   **uv (推荐)**: 一个极速的 Python 包管理器。
    -   macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
    -   Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

## 2. 安装与配置

请按照以下步骤来设置和配置项目。

### 步骤 2.1: 克隆并进入项目
```bash
# git clone <your-repo-url>
cd <your-project-directory>
```

### 步骤 2.2: 创建并激活 Python 虚拟环境
我们推荐使用 `uv` 来创建虚拟环境。
```bash
# 使用 uv 创建虚拟环境
uv venv

# 激活虚拟环境
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```
激活成功后，您的终端提示符前应该会有一个 `(.venv)` 标志。

### 步骤 2.3: 安装依赖
使用 `requirements.txt` 文件来安装所有必需的 Python 库。
```bash
uv pip install -r requirements.txt
```

### 步骤 2.4: 创建配置文件
您需要创建两个配置文件来存放密钥和服务器信息。

1.  **创建 `.env` 文件 (用于 API 密钥)**
    在项目根目录创建一个名为 `.env` 的文件，并填入您的 Google API 密钥。
    ```env
    # .env
    GOOGLE_API_KEY="在这里粘贴您从 Google AI Studio 获取的 API 密钥"
    ```

2.  **创建 `config.json` 文件 (用于服务器配置)**
    在项目根目录创建一个名为 `config.json` 的文件。这个文件告诉程序如何启动 Playwright Docker 容器，以及启动后如何通过网络连接到它。
    ```json
    {
      "mcpServers": {
        "playwright": {
          "command": "docker",
          "args": [
            "run",
            "-i",
            "--rm",
            "--init",
            "--pull=always",
            "-p", "8931:8931",
            "mcr.microsoft.com/playwright/mcp",
            "--port", "8931"
          ],
          "url": "http://localhost:8931/mcp"
        }
      }
    }
    ```

## 3. 运行机器人

所有配置完成后，您只需一个命令即可启动整个系统。

```bash
python3 chat.py
```
**会发生什么？**
-   程序会首先在后台启动一个 Docker 容器。如果是第一次运行，Docker 会自动下载 `mcr.microsoft.com/playwright/mcp` 镜像，这可能需要一些时间。
-   等待几秒钟让容器内的服务启动后，程序会连接到它。
-   连接成功后，您会看到欢迎信息和机器人就绪的提示。

## 4. 如何使用

机器人就绪后，您可以直接在 `👤 你:` 提示符后输入自然语言指令。

**示例指令:**
-   **简单导航**: `navigate to https://www.google.com`
-   **获取内容并总结**: `总结这个网页的内容：https://www.nhk.or.jp/`
-   **多步任务**: `打开 aomodel.com，然后搜索 '最新的AI新闻', 告诉我第一个结果的标题`

**如何退出:**
在 `👤 你:` 提示符后，输入 `exit` 或 `quit` 并按回车，程序将会安全地关闭 Docker 容器并退出。