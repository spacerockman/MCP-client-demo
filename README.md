# AI 浏览器代理库

这是一个可重用的 Python 库，它提供了一个 AI 驱动的浏览器代理，能够理解自然语言指令并执行复杂的网页自动化任务。

这个库的核心是 `BrowserAgent` 类，它可以被任何其他 Python 项目导入和使用，为其赋予强大的、由 AI 控制的浏览器操作能力。

## 1. 核心功能

-   **自然语言控制**：接受人类语言作为指令（例如，“总结这个网页”）。
-   **Playwright 驱动**：在后台使用 Playwright 来确保强大的浏览器兼容性。
-   **Docker 化执行**：所有浏览器操作都在一个隔离的、无需 `sudo` 权限的 Docker 容器中执行，保证了环境的纯净和安全。
-   **可插拔的 AI**：当前使用 Google Gemini，但其架构易于扩展。

## 2. 安装与配置 (最终的正确流程)

### 步骤 2.1: 环境准备
-   **Python 3.10+**
-   **Docker**: 确保 Docker 服务正在运行。
-   **uv (推荐)**: 一个极速的 Python 包管理器。

### 步骤 2.2: 创建依赖声明文件
在您的项目中，创建一个名为 `requirements.in` 的文件。这个文件只包含您项目**直接**使用的库。
```text
# requirements.in
google-generativeai
python-dotenv
fastmcp
```

### 步骤 2.3: 编译并安装依赖
我们将使用 `uv` 来自动解决并安装所有必需的依赖。

1.  **创建并激活虚拟环境**
    ```bash
    uv venv
    source .venv/bin/activate
    ```

2.  **编译完整的依赖列表**
    这个命令会读取 `requirements.in` 并生成一个包含所有子依赖及其精确版本的 `requirements.txt` 文件。
    ```bash
    uv pip compile requirements.in -o requirements.txt
    ```

3.  **同步您的环境**
    这个命令会严格按照新生成的 `requirements.txt` 来安装所有包。
    ```bash
    uv pip sync requirements.txt
    ```

### 步骤 2.4: 创建配置文件
在您的项目根目录中，需要放置以下两个配置文件。

1.  **`.env` 文件 (用于 API 密钥)**
    ```env
    # .env
    GOOGLE_API_KEY="your-google-api-key"
    ```

2.  **`config.json` 文件 (用于服务器配置)**
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

## 3. 如何使用 (集成到您的项目中)

将 `browser_agent.py` 文件复制到您的项目中，然后像下面这样使用它。`example_usage.py` 文件是一个完整的、可运行的示例。

```python
# 在您的项目代码中 (例如 "项目 A")
import asyncio
from browser_agent import BrowserAgent

async def my_web_task():
    # 1. 创建代理实例
    agent = BrowserAgent()

    # 2. 异步初始化代理 (这个昂贵的操作应该只在程序启动时执行一次)
    await agent.initialize()

    # 3. 假设您的项目通过 web search 得到了一个 URL
    found_url = "https://www.nhk.or.jp/..."
    prompt_for_agent = f"请访问 {found_url} 并总结其主要内容。"

    # 4. 调用代理来处理这个 URL
    summary = await agent.run_task(prompt_for_agent)

    # 5. 使用代理返回的结果
    print("网页总结:")
    print(summary)


# 运行您的异步函数
if __name__ == "__main__":
    asyncio.run(my_web_task())
```

## 4. 运行示例

要运行本项目自带的示例，只需执行：
```bash
python3 example_usage.py
```