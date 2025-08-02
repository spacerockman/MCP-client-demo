import asyncio
import json
import os
import logging
import subprocess

# 经过验证的库
import google.generativeai as genai
from google.generativeai.types import Tool as GeminiTool, FunctionDeclaration
from dotenv import load_dotenv
from fastmcp import Client as MCPClient

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [BrowserAgent] - %(message)s')

class BrowserAgent:
    """
    一个 AI 驱动的浏览器代理，能够理解自然语言指令并执行网页自动化任务。
    """

    def __init__(self):
        """初始化代理，但尚未加载配置或模型。"""
        self.model = None
        self.mcp_command = None
        self.mcp_url = None
        self.is_initialized = False

    async def initialize(self):
        """
        异步加载配置，获取工具定义，并初始化 LLM 模型。
        这是一个昂贵的操作，应该只执行一次。
        """
        if self.is_initialized:
            logging.info("代理已初始化，跳过。")
            return

        logging.info("正在初始化浏览器代理...")
        self._load_config()
        
        print("正在进行一次性工具定义检查...")
        gemini_tools = await self._get_initial_tool_schema()
        if not gemini_tools:
            raise RuntimeError("无法在启动时获取工具定义，初始化失败。")
        print("✅ 工具定义检查完成。")

        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

        system_instruction = (
            "你是一个AI助手，你的任务是使用提供的工具来控制一个网络浏览器，以完成用户的请求。"
            "请仔细分析用户的需求，并按顺序调用一个或多个工具来达成目标。"
            "你的第一步几乎永远是调用 'browser_navigate' 工具。"
            "在与页面交互后，你应该调用 'browser_snapshot' 来查看页面的当前状态，以决定下一步行动。"
        )

        self.model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            tools=gemini_tools,
            system_instruction=system_instruction
        )
        self.is_initialized = True
        logging.info(f"✅ 代理初始化完成，模型: {self.model.model_name}")

    def _load_config(self):
        """从 .env 和 config.json 加载配置。"""
        load_dotenv()
        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("环境变量 'GOOGLE_API_KEY' 未在 .env 文件中设置。")
        
        with open("config.json", 'r') as f:
            config_data = json.load(f)
        
        playwright_config = config_data["mcpServers"]["playwright"]
        self.mcp_command = [playwright_config["command"]] + playwright_config.get("args", [])
        self.mcp_url = playwright_config["url"]
        
        if not self.mcp_command or not self.mcp_url:
            raise ValueError("配置文件中必须同时包含 'command' 和 'url'。")
        logging.info("✅ 配置加载成功。")

    async def run_task(self, user_prompt: str) -> str:
        """
        执行一个独立的浏览器任务。
        """
        if not self.is_initialized:
            raise RuntimeError("代理尚未初始化。请在使用前调用 await agent.initialize()")

        process = None
        try:
            logging.info(f"为任务启动 Docker 进程: {' '.join(self.mcp_command)}")
            process = subprocess.Popen(self.mcp_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            await asyncio.sleep(8) # 等待 Docker 容器启动

            async with MCPClient(self.mcp_url) as mcp_client:
                logging.info(f"✅ 成功连接到 MCP 服务器: {self.mcp_url}")
                
                chat = self.model.start_chat()
                
                logging.info(f"正在将任务发送给 Gemini: '{user_prompt}'")
                response = await chat.send_message_async(user_prompt)

                # *** 这是最终的、决定性的修改：处理并行的工具调用 ***
                while True:
                    # 检查响应中是否有任何工具调用
                    if not (response.candidates and response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call):
                        break # 如果没有工具调用，则退出循环

                    # 收集当前轮次的所有工具调用请求
                    tool_calls = [part.function_call for part in response.candidates[0].content.parts if part.function_call]
                    
                    if not tool_calls:
                        break

                    tool_response_parts = []
                    
                    # 依次执行所有请求的工具
                    for fc in tool_calls:
                        tool_name = fc.name
                        tool_args = {key: value for key, value in fc.args.items()}
                        logging.info(f"Gemini 请求调用工具: {tool_name}，参数: {tool_args}")
                        
                        tool_result = await mcp_client.call_tool(tool_name, tool_args)
                        logging.info(f"工具返回结果: {str(tool_result)[:300]}...")
                        
                        # 为本次调用准备好响应部分
                        tool_response_parts.append({
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": str(tool_result)}
                            }
                        })
                    
                    # 将所有工具调用的结果一次性发回
                    logging.info(f"正在将 {len(tool_response_parts)} 个工具的结果发回 Gemini...")
                    response = await chat.send_message_async(tool_response_parts)

                final_text = response.text
                logging.info(f"任务完成，最终响应: {final_text}")
                return final_text

        finally:
            if process:
                logging.info("正在终结任务的 Docker 进程...")
                process.terminate()
                process.wait()
                logging.info("Docker 进程已终结。")

    async def _get_initial_tool_schema(self) -> list[GeminiTool] | None:
        """辅助函数，仅用于在初始化时获取一次工具的 schema。"""
        process = None
        try:
            process = subprocess.Popen(self.mcp_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(8)
            async with MCPClient(self.mcp_url) as mcp_client:
                tool_summaries = await mcp_client.list_tools()
                return self._convert_summaries_to_gemini_tools(tool_summaries)
        except Exception as e:
            logging.error(f"获取初始工具定义时出错: {e}")
            return None
        finally:
            if process:
                process.terminate()
                process.wait()

    def _convert_summaries_to_gemini_tools(self, tool_summaries: list) -> list[GeminiTool]:
        """将 MCP 工具转换为 Gemini 格式。"""
        function_declarations = []
        for tool_summary in tool_summaries:
            input_schema = tool_summary.inputSchema
            properties = input_schema.get('properties', {})
            required = input_schema.get('required', [])
            
            for param_name, param_details in properties.items():
                if 'type' not in param_details:
                    param_details['type'] = 'string'

            func_decl = FunctionDeclaration(
                name=tool_summary.name,
                description=tool_summary.description,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            )
            function_declarations.append(func_decl)
        return [GeminiTool(function_declarations=function_declarations)] if function_declarations else []