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