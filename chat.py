import asyncio
import json
import os
import logging
import sys
import subprocess
from abc import ABC, abstractmethod

# 经过验证的库
import google.generativeai as genai
from google.generativeai.types import Tool as GeminiTool, FunctionDeclaration
from openai import OpenAI, AzureOpenAI
from dotenv import load_dotenv
from fastmcp import Client as MCPClient

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [BOT] - %(message)s')

# --- 1. 抽象基类定义 ---
class LLMHandler(ABC):
    """定义所有 LLM 处理器必须遵循的接口。"""
    @abstractmethod
    def __init__(self, config: dict):
        pass

    @abstractmethod
    def convert_mcp_tools_to_llm_format(self, tool_summaries: list) -> list:
        """将 MCP 工具列表转换为特定 LLM 的格式。"""
        pass

    @abstractmethod
    async def get_response(self, user_input: str, mcp_command: list, mcp_url: str, chat_history: list):
        """处理单个请求的完整生命周期。"""
        pass

# --- 2. Gemini 实现 ---
class GeminiHandler(LLMHandler):
    def __init__(self, config: dict):
        self.model_name = config.get("model_name")
        self.system_instruction = config.get("system_instruction")
        self.model = None

    def convert_mcp_tools_to_llm_format(self, tool_summaries: list) -> list[GeminiTool]:
        function_declarations = []
        for tool_summary in tool_summaries:
            input_schema = tool_summary.inputSchema
            properties = input_schema.get('properties', {})
            required = input_schema.get('required', [])
            for param_name, param_details in properties.items():
                if 'type' not in param_details:
                    param_details['type'] = 'string'
            func_decl = FunctionDeclaration(name=tool_summary.name, description=tool_summary.description,
                                            parameters={"type": "object", "properties": properties, "required": required})
            function_declarations.append(func_decl)
        return [GeminiTool(function_declarations=function_declarations)] if function_declarations else []

    async def get_response(self, user_input: str, mcp_command: list, mcp_url: str, chat_history: list):
        if not self.model:
            print("正在为 Gemini 进行一次性工具定义检查...")
            gemini_tools = await get_initial_tool_schema(mcp_command, mcp_url, self.convert_mcp_tools_to_llm_format)
            if not gemini_tools:
                raise RuntimeError("无法在启动时获取工具定义。")
            self.model = genai.GenerativeModel(model_name=self.model_name, tools=gemini_tools, system_instruction=self.system_instruction)
            print(f"✅ Gemini 模型 '{self.model_name}' 初始化完成。")

        process = None
        try:
            logging.info(f"为新请求启动 Docker 进程...")
            process = subprocess.Popen(mcp_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(5)

            async with MCPClient(mcp_url) as mcp_client:
                logging.info(f"✅ 成功连接到 MCP 服务器: {mcp_url}")
                chat = self.model.start_chat(history=chat_history)
                
                print("🤔 LLM 正在思考中，请稍候...")
                response = await chat.send_message_async(user_input)

                while response.candidates and response.candidates[0].content.parts[0].function_call:
                    fc = response.candidates[0].content.parts[0].function_call
                    tool_name = fc.name
                    tool_args = {key: value for key, value in fc.args.items()}
                    logging.info(f"LLM 请求调用工具: {tool_name}，参数: {tool_args}")
                    tool_result = await mcp_client.call_tool(tool_name, tool_args)
                    logging.info(f"工具返回结果: {str(tool_result)[:300]}...")
                    
                    print("🤔 LLM 正在处理工具结果，请稍候...")
                    tool_response_part = {"function_response": {"name": tool_name, "response": {"result": str(tool_result)}}}
                    response = await chat.send_message_async(tool_response_part)

                print(f"✨ Gemini: {response.text}")
                chat_history.extend(chat.history)
        finally:
            if process:
                logging.info("正在终结本次会话的 Docker 进程...")
                process.terminate()
                process.wait()

# --- 3. OpenAI / Azure 实现 ---
class OpenAIHandler(LLMHandler):
    def __init__(self, config: dict):
        provider = config.get("provider")
        if provider == "azure":
            self.client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            self.model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        else: # "openai"
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model_name = config.get("model_name")
        self.system_instruction = {"role": "system", "content": config.get("system_instruction")}
        self.tools = None

    def convert_mcp_tools_to_llm_format(self, tool_summaries: list) -> list:
        openai_tools = []
        for tool_summary in tool_summaries:
            input_schema = tool_summary.inputSchema
            properties = input_schema.get('properties', {})
            required = input_schema.get('required', [])
            for param_name, param_details in properties.items():
                if 'type' not in param_details:
                    param_details['type'] = 'string'
            
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool_summary.name,
                    "description": tool_summary.description,
                    "parameters": {"type": "object", "properties": properties, "required": required}
                }
            })
        return openai_tools

    async def get_response(self, user_input: str, mcp_command: list, mcp_url: str, chat_history: list):
        if not self.tools:
            print(f"正在为 {self.client.__class__.__name__} 进行一次性工具定义检查...")
            self.tools = await get_initial_tool_schema(mcp_command, mcp_url, self.convert_mcp_tools_to_llm_format)
            if not self.tools:
                raise RuntimeError("无法在启动时获取工具定义。")
            print(f"✅ OpenAI/Azure 模型 '{self.model_name}' 初始化完成。")

        process = None
        try:
            logging.info(f"为新请求启动 Docker 进程...")
            process = subprocess.Popen(mcp_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(5)

            async with MCPClient(mcp_url) as mcp_client:
                logging.info(f"✅ 成功连接到 MCP 服务器: {mcp_url}")
                
                messages = [self.system_instruction] + chat_history + [{"role": "user", "content": user_input}]
                
                while True:
                    print("🤔 LLM 正在思考中，请稍候...")
                    response = self.client.chat.completions.create(model=self.model_name, messages=messages, tools=self.tools)
                    response_message = response.choices[0].message
                    
                    if not response_message.tool_calls:
                        final_text = response_message.content
                        print(f"✨ OpenAI/Azure: {final_text}")
                        chat_history.append({"role": "user", "content": user_input})
                        chat_history.append({"role": "assistant", "content": final_text})
                        break
                    
                    messages.append(response_message)
                    for tool_call in response_message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)
                        logging.info(f"LLM 请求调用工具: {function_name}，参数: {function_args}")
                        
                        print("🤔 LLM 正在处理工具结果，请稍候...")
                        tool_result = await mcp_client.call_tool(function_name, function_args)
                        logging.info(f"工具返回结果: {str(tool_result)[:300]}...")
                        
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": str(tool_result),
                        })
        finally:
            if process:
                logging.info("正在终结本次会话的 Docker 进程...")
                process.terminate()
                process.wait()

# --- 4. 主程序逻辑 ---
def load_mcp_config():
    """只从 config.json 加载 MCP 服务器配置。"""
    try:
        with open("config.json", 'r') as f:
            config = json.load(f)
        playwright_config = config["mcpServers"]["playwright"]
        command = [playwright_config["command"]] + playwright_config.get("args", [])
        url = playwright_config["url"]
        return command, url
    except Exception as e:
        logging.error(f"🚨 MCP 配置加载失败: {e}")
        return None, None

async def main():
    """主程序，根据代码内设置选择并运行 LLM 处理器。"""
    
    # *** 这是关键的修改：在这里选择要使用的 LLM 提供商 ***
    # 可选项: "gemini", "openai", "azure"
    LLM_PROVIDER_TO_USE = "gemini"
    
    # 加载 .env 文件中的所有环境变量
    load_dotenv()

    mcp_command, mcp_url = load_mcp_config()
    if not mcp_command or not mcp_url:
        return

    system_instruction = (
        "你是一位顶级的网络自动化专家，你的任务是精确地使用工具集来操作一个真实的浏览器，以完成用户的指令。"
        "在执行任何操作之前，请始终遵循以下核心原则和工作流程。"
        "## 核心原则"
        "1.  **观察优先 (Observe First)**：在进行任何交互（如点击、输入）之前，必须先使用 `browser_snapshot` 工具来理解当前的页面结构和可用元素。不要在盲目的情况下行动。"
        "2.  **任务分解 (Decomposition)**：对于复杂的用户请求（例如“预订一张从A到B的机票”），先在心中构思一个清晰的、分步骤的计划。例如：1. 打开订票网站 -> 2. 输入出发地 -> 3. 输入目的地 -> 4. 选择日期 -> 5. 点击搜索。"
        "3.  **精准定位 (Precise Targeting)**：在调用 `browser_click` 或 `browser_type` 等交互工具时，优先选择具有唯一ID、`data-testid` 或其他稳定属性的元素。如果不行，再考虑使用文本内容或CSS选择器，但要确保其独特性。"
        "4.  **主动等待 (Proactive Waiting)**：现代网页是动态加载的。在尝试与某个元素交互之前，如果怀疑它不是立即出现的，请先使用 `browser_wait_for` 等待该元素变得可见或可交互。这能极大提高成功率。"
        "5.  **结果验证 (Verify Results)**：每次执行完一个关键动作（如导航、点击、表单提交）后，都要通过 `browser_snapshot` 再次观察页面，确认你的操作是否达到了预期的效果（例如，是否跳转到了新页面，是否出现了新的元素）。"

        "## 标准工作流程"
        "1.  **分析需求**：仔细阅读用户的最终目标。"
        "2.  **初始导航**：如果当前不在目标网站，第一步应使用 `browser_navigate` 前往。对于不确定的任务，导航到Google等搜索引擎进行初步探索。"
        "3.  **观察与计划**：使用 `browser_snapshot` 捕获当前页面信息，并根据你的任务分解计划，确定下一步要交互的元素。"
        "4.  **执行单步**：调用一个工具（如 `browser_click`, `browser_type`）完成计划中的一步。"
        "5.  **验证与循环**：再次使用 `browser_snapshot` 验证上一步的结果。如果成功，则继续执行计划的下一步；如果失败，则进入下面的“失败恢复”流程。"

        "## 失败恢复与特殊情况"
        "- **元素未找到**：如果你的选择器找不到元素，不要立即放弃。首先，使用 `browser_snapshot` 查看当前页面是否符合预期。页面可能加载缓慢、弹出了对话框，或者你的上一步操作失败了。根据观察调整你的策略。"
        "- **处理弹窗**：如果出现浏览器原生弹窗（Alert, Confirm, Prompt），请使用 `browser_handle_dialog` 工具来处理。"
        "- **遇到核心障碍（如验证码或登录墙）**："
            "**1. 不要立即放弃并向用户报告失败。你的首要任务是寻找完成用户目标的替代路径。**"
            "**2. 识别障碍类型：这是一个验证码（CAPTCHA）？一个强制登录页面？还是一个付费墙？**"
            "**3. 采取规避策略：**"
                "- **对于搜索引擎的验证码：** 如果在某个搜索引擎（如 `google.com`）上遇到验证码，**立即放弃该网站，并切换到另一个搜索引擎**。例如，尝试使用 `bing.com`、`duckduckgo.com` 或 `baidu.com` 来执行相同的搜索。这是处理此问题的首选策略。"
                "- **对于特定网站的障碍：** 如果任务是获取新闻或信息，而目标网站被挡住，可以尝试去搜索引擎搜索相同的主题，寻找其他可以提供相似信息且没有障碍的新闻来源或网站。"
            "**4. 最后的手段：** 只有在尝试了多种替代网站和方法（例如，至少尝试了1-2个其他搜索引擎或信息来源）后仍然失败时，才能向用户报告此障碍，并解释你已经尝试过的所有替代方案。"
    )


    # 在代码中定义 LLM 配置
    llm_configs = {
        "gemini": {"model_name": "gemini-2.5-flash"},
        "openai": {"model_name": "gpt-4-turbo"},
        "azure": {} # Azure 的模型名称直接从 .env 读取
    }
    
    current_llm_config = llm_configs.get(LLM_PROVIDER_TO_USE, {})
    current_llm_config["system_instruction"] = system_instruction
    current_llm_config["provider"] = LLM_PROVIDER_TO_USE

    handler: LLMHandler
    if LLM_PROVIDER_TO_USE == "gemini":
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        handler = GeminiHandler(current_llm_config)
    elif LLM_PROVIDER_TO_USE in ["openai", "azure"]:
        handler = OpenAIHandler(current_llm_config)
    else:
        logging.error(f"未知的 LLM 提供商: '{LLM_PROVIDER_TO_USE}'。请在代码中选择 'gemini', 'openai', 或 'azure'。")
        return

    chat_history = []
    print(f"\n--- 🤖 浏览器控制机器人已就绪 (提供商: {LLM_PROVIDER_TO_USE.upper()}) ---")
    print("现在可以直接下达指令。")

    while True:
        try:
            user_input = input("\n👤 你: ").strip()
            if not user_input:
                print("⚠️ 请输入内容，或使用 'exit' 退出。")
                continue
            if user_input.lower() in ['exit', 'quit']:
                print("👋 正在关闭...")
                break
            
            await handler.get_response(user_input, mcp_command, mcp_url, chat_history)
        
        except Exception as e:
            logging.error(f"🚨 本轮对话出现严重错误: {e}")
            print("抱歉，处理您的请求时遇到了问题。请尝试重新提问，或使用 'exit' 退出。")

async def get_initial_tool_schema(command: list, url: str, converter) -> list | None:
    """一个辅助函数，仅用于在程序启动时获取一次工具的 schema。"""
    process = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(8)
        async with MCPClient(url) as mcp_client:
            tool_summaries = await mcp_client.list_tools()
            return converter(tool_summaries)
    except Exception as e:
        logging.error(f"获取初始工具定义时出错: {e}")
        return None
    finally:
        if process:
            process.terminate()
            process.wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断。")