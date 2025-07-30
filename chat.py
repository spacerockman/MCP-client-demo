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
        "你是一个AI助手，你的任务是使用提供的工具来控制一个网络浏览器，以完成用户的请求。"
        "请仔细分析用户的需求，并按顺序调用一个或多个工具来达成目标。"
        "对于特定任务，请优先选择直接的网站。例如，要查询天气，请直接导航到一个天气网站，而不是在谷歌搜索。"
        "你的第一步几乎永远是调用 'browser_navigate' 工具。"
        "如果遇到任何无法处理的页面（如'我不是机器人'验证码），请报告这个问题并停止当前任务，而不是尝试与之交互。"
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