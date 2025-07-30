import asyncio
import json
import os
import logging
import sys
import subprocess # 使用 Python 标准库来管理子进程

# 经过验证的库
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
            
        logging.info("✅ 配置加载成功。")
        return api_key, command, url
        
    except KeyError as e:
        logging.error(f"🚨 配置加载失败: 配置文件中缺少关键字段 {e}。请确保 config.json 包含 command, args, 和 url。")
        return None, None, None
    except Exception as e:
        logging.error(f"🚨 配置加载失败: {e}")
        return None, None, None

def convert_summaries_to_gemini_tools(tool_summaries: list) -> list[GeminiTool]:
    """仅使用工具摘要（名称和描述）来创建Gemini工具。"""
    function_declarations = []
    for tool_summary in tool_summaries:
        func_decl = FunctionDeclaration(
            name=tool_summary.name,
            description=tool_summary.description,
        )
        function_declarations.append(func_decl)
    return [GeminiTool(function_declarations=function_declarations)] if function_declarations else []

async def main():
    """主程序，手动管理子进程，并通过网络连接。"""
    api_key, command, url = load_config()
    if not api_key or not command or not url:
        return

    process = None
    try:
        # 步骤 1: 使用 subprocess.Popen 在后台启动 Docker 容器
        logging.info(f"正在后台启动 Docker 进程: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 步骤 2: 等待几秒，让容器有时间完全启动并开始监听端口
        wait_time = 8
        logging.info(f"等待 {wait_time} 秒让 Docker 容器启动...")
        await asyncio.sleep(wait_time)
        logging.info("继续执行，尝试连接...")

        # 步骤 3: 使用 fastmcp 唯一可靠的方式——通过 URL 连接
        async with MCPClient(url) as mcp_client:
            logging.info(f"✅ 成功连接到 MCP 服务器: {url}")
            
            tool_summaries = await mcp_client.list_tools()
            if not tool_summaries:
                logging.error("🚨 无法从 MCP 服务器获取任何工具。")
                return
            
            # 打印获取到的工具列表
            logging.info(f"从服务器获取到 {len(tool_summaries)} 个工具的摘要。详情如下:")
            print("\n--- 🤖 可用工具列表 ---")
            for tool in tool_summaries:
                print(f"  - {tool.name}: {tool.description}")
            print("------------------------\n")


            gemini_tools = convert_summaries_to_gemini_tools(tool_summaries)

            genai.configure(api_key=api_key)
            
            # *** 模型名称指定处 ***
            # 'gemini-1.5-flash-latest' 是对 "Flash" 系列最新模型的正确引用
            model = genai.GenerativeModel(
                model_name='gemini-2.5-flash',
                tools=gemini_tools
            )
            chat = model.start_chat()

            print("--- 🤖 Gemini 浏览器控制机器人已就绪 (Docker 模式) ---")
            print(f"✅ 模型已设置为: {model.model_name}") # 打印确认模型名称
            print("机器人已自动启动 Playwright Docker 容器。")
            print("现在可以直接下达指令。")

            # ... 聊天循环 ...
            while True:
                user_input = input("\n👤 你: ")
                if user_input.lower() in ['exit', 'quit']:
                    print("👋 正在关闭...")
                    break
                
                # 增加交互日志
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
                    
                    logging.info("正在将工具结果发回 Gemini...")
                    response = await chat.send_message_async(
                        genai.Part(function_response=genai.FunctionResponse(name=tool_name, response={"result": str(tool_result)}))
                    )
                    logging.info("已收到 Gemini 对工具结果的最终响应。")

                print(f"✨ Gemini: {response.text}")

    except Exception as e:
        logging.error(f"🚨 发生严重错误: {e}")
        if isinstance(e, FileNotFoundError):
             logging.error("提示: 找不到 'docker' 命令。请确保 Docker 已经安装并且正在运行。")
    finally:
        # 步骤 4: 确保 Docker 容器在程序退出时被终结
        if process:
            logging.info("正在终结 Docker 进程...")
            process.terminate()
            process.wait()
            logging.info("Docker 进程已终结。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断。")