import asyncio
import json
import os
import logging
import sys
import subprocess
import google.generativeai as genai
from google.generativeai.types import Tool as GeminiTool, FunctionDeclaration
from dotenv import load_dotenv
from fastmcp import Client as MCPClient

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [BOT] - %(message)s')

def load_config():
    """从 config.json 加载 command 和 url。"""
    try:
        load_dotenv()
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("环境变量 'GOOGLE_API_KEY' 未在 .env 文件中设置。")
        
        with open("config.json", 'r') as f:
            config_data = json.load(f)
        
        playwright_config = config_data["mcpServers"]["playwright"]
        command = [playwright_config["command"]] + playwright_config.get("args", [])
        url = playwright_config["url"]
        
        if not command or not url:
            raise ValueError("配置文件中必须同时包含 'command' 和 'url'。")
            
        logging.info("✅ 初始配置加载成功。")
        return api_key, command, url
        
    except KeyError as e:
        logging.error(f"🚨 配置加载失败: 配置文件中缺少关键字段 {e}。")
        return None, None, None
    except Exception as e:
        logging.error(f"🚨 配置加载失败: {e}")
        return None, None, None

def convert_summaries_to_gemini_tools(tool_summaries: list) -> list[GeminiTool]:
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

async def handle_single_request(user_input: str, command: list, url: str, model, chat_history: list):
    """
    为单次用户请求处理完整的 Docker 启动、MCP 连接和 Gemini 交互流程。
    """
    process = None
    try:
        logging.info(f"为新请求启动 Docker 进程: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        wait_time = 3
        logging.info(f"等待 {wait_time} 秒让 Docker 容器启动...")
        await asyncio.sleep(wait_time)
        logging.info("继续执行，尝试连接...")

        async with MCPClient(url) as mcp_client:
            logging.info(f"✅ 成功连接到 MCP 服务器: {url}")
            
            # 重新开始一个聊天会话，但保留历史记录
            chat = model.start_chat(history=chat_history)
            
            print("🤔 Gemini 正在思考中，请稍候...")
            logging.info(f"正在将用户输入发送给 Gemini: '{user_input}'")
            response = await chat.send_message_async(user_input)
            logging.info("已从 Gemini 收到响应。正在检查工具调用...")

            while response.candidates and response.candidates[0].content.parts[0].function_call:
                fc = response.candidates[0].content.parts[0].function_call
                tool_name = fc.name
                tool_args = {key: value for key, value in fc.args.items()}
                logging.info(f"Gemini 请求调用工具: {tool_name}，参数: {tool_args}")
                tool_result = await mcp_client.call_tool(tool_name, tool_args)
                logging.info(f"工具返回结果: {str(tool_result)[:300]}...")
                
                print("🤔 Gemini 正在处理工具结果，请稍候...")
                logging.info("正在将工具结果发回 Gemini...")
                
                tool_response_part = {
                    "function_response": {
                        "name": tool_name,
                        "response": {"result": str(tool_result)}
                    }
                }
                
                response = await chat.send_message_async(tool_response_part)
                logging.info("已收到 Gemini 对工具结果的最终响应。")

            print(f"✨ Gemini: {response.text}")
            # 更新聊天历史
            chat_history.extend(chat.history)

    finally:
        if process:
            logging.info("正在终结本次会话的 Docker 进程...")
            process.terminate()
            process.wait()
            logging.info("Docker 进程已终结。")

async def main():
    """主程序，初始化模型，并在循环中为每个请求创建独立的会话。"""
    api_key, command, url = load_config()
    if not api_key or not command or not url:
        return

    # 在程序启动时，只获取一次工具定义
    # 这是一个优化，假设工具集不会在运行时改变
    print("正在进行一次性工具定义检查...")
    gemini_tools = await get_initial_tool_schema(command, url)
    if not gemini_tools:
        logging.error("无法在启动时获取工具定义，程序终止。")
        return
    print("✅ 工具定义检查完成。")

    genai.configure(api_key=api_key)

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
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        tools=gemini_tools,
        system_instruction=system_instruction
    )
    
    chat_history = [] # 用于在多次请求之间保持对话上下文

    print("\n--- 🤖 Gemini 浏览器控制机器人已就绪 (会话模式) ---")
    print(f"✅ 模型已设置为: {model.model_name}")
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
            
            # 为每个请求调用独立的处理器
            await handle_single_request(user_input, command, url, model, chat_history)
        
        except Exception as e:
            logging.error(f"🚨 本轮对话出现严重错误: {e}")
            print("抱歉，处理您的请求时遇到了问题。请尝试重新提问，或使用 'exit' 退出。")

async def get_initial_tool_schema(command: list, url: str) -> list[GeminiTool] | None:
    """
    一个辅助函数，仅用于在程序启动时获取一次工具的 schema。
    """
    process = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(8)
        async with MCPClient(url) as mcp_client:
            tool_summaries = await mcp_client.list_tools()
            return convert_summaries_to_gemini_tools(tool_summaries)
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
