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
        "你是一个AI助手，你的任务是使用提供的工具来控制一个网络浏览器，以完成用户的请求。"
        "请仔细分析用户的需求，并按顺序调用一个或多个工具来达成目标。"
        "对于特定任务，请优先选择直接的网站。例如，要查询天气，请直接导航到一个天气网站，而不是在谷歌搜索。"
        "你的第一步几乎永远是调用 'browser_navigate' 工具。"
        "如果遇到任何无法处理的页面（如'我不是机器人'验证码），请报告这个问题并停止当前任务，而不是尝试与之交互。"
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
