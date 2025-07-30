# 多模型 AI 浏览器控制机器人

这是一个 AI 驱动的聊天机器人，它可以使用 **Google Gemini**, **OpenAI API**, 或 **Azure OpenAI** 来理解自然语言指令，并通过 Playwright MCP 服务器来控制一个真实的浏览器，以完成网页自动化任务。

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
```bash
# 使用 uv 创建虚拟环境
uv venv

# 激活虚拟环境
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

### 步骤 2.3: 安装依赖
使用 `requirements.txt` 文件来安装所有必需的 Python 库。
```bash
uv pip install -r requirements.txt
```

### 步骤 2.4: 创建配置文件
您需要创建两个配置文件。

1.  **创建 `.env` 文件 (用于 API 密钥)**
    在项目根目录创建一个名为 `.env` 的文件，并根据您要使用的服务，填入相应的 API 密钥。
    ```env
    # .env

    # --- Google Gemini ---
    GOOGLE_API_KEY="your-google-api-key"

    # --- OpenAI ---
    OPENAI_API_KEY="your-openai-api-key"

    # --- Azure OpenAI ---
    AZURE_OPENAI_KEY="your-azure-openai-service-key"
    AZURE_OPENAI_ENDPOINT="https://your-azure-endpoint.openai.azure.com/"
    AZURE_OPENAI_DEPLOYMENT_NAME="your-deployment-name"
    AZURE_OPENAI_API_VERSION="2024-02-01"
    ```

2.  **创建 `config.json` 文件 (用于服务器配置)**
    在项目根目录创建一个名为 `config.json` 的文件。**此文件只包含 MCP 服务器的配置。**
    ```json
    {
      "mcpServers": {
        "playwright": {
          "command": "docker",
          "args": [
            "run", "-i", "--rm", "--init", "--pull=always",
            "-p", "8931:8931",
            "mcr.microsoft.com/playwright/mcp",
            "--port", "8931"
          ],
          "url": "http://localhost:8931/mcp"
        }
      }
    }
    ```

### 步骤 2.5: 在代码中选择要使用的 LLM
打开 `chat.py` 文件，找到 `main()` 函数顶部的 `LLM_PROVIDER_TO_USE` 变量，并将其值修改为您想使用的服务。
```python
# chat.py

async def main():
    """主程序，根据代码内设置选择并运行 LLM 处理器。"""
    
    # *** 在这里选择要使用的 LLM 提供商 ***
    # 可选项: "gemini", "openai", "azure"
    LLM_PROVIDER_TO_USE = "gemini"
    
    # ... (代码其余部分)
```

## 3. 运行机器人

所有配置完成后，您只需一个命令即可启动整个系统。

```bash
python3 chat.py
```
程序会根据您在 `chat.py` 中设置的 `LLM_PROVIDER_TO_USE` 变量，自动选择并初始化正确的 AI 模型。

## 4. 如何使用

机器人就绪后，您可以直接在 `👤 你:` 提示符后输入自然语言指令。

**示例指令:**
-   **简单导航**: `navigate to https://www.google.com`
-   **获取内容并总结**: `总结这个网页的内容：https://www.nhk.or.jp/`
-   **多步任务**: `打开 aomodel.com，然后搜索 '最新的AI新闻', 告诉我第一个结果的标题`

**如何退出:**
在 `👤 你:` 提示符后，输入 `exit` 或 `quit` 并按回车。