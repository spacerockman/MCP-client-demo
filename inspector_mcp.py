import asyncio
import json
import os
import logging
import sys
import subprocess

# 这是一个安全的诊断脚本，用于检查 fastmcp.list_tools() 返回对象的真实内容

from fastmcp import Client as MCPClient

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [INSPECTOR] - %(message)s')

def load_config():
    """从 config.json 加载 command 和 url。"""
    try:
        with open("config.json", 'r') as f:
            config_data = json.load(f)
        
        playwright_config = config_data["mcpServers"]["playwright"]
        command = [playwright_config["command"]] + playwright_config.get("args", [])
        url = playwright_config["url"]
        
        if not command or not url:
            raise ValueError("配置文件中必须同时包含 'command' 和 'url'。")
            
        logging.info("✅ 配置加载成功。")
        return command, url
        
    except Exception as e:
        logging.error(f"🚨 配置加载失败: {e}")
        return None, None

async def main():
    """主程序，连接服务器并详细检查返回的工具对象。"""
    command, url = load_config()
    if not command or not url:
        return

    process = None
    try:
        logging.info(f"正在后台启动 Docker 进程: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        wait_time = 5 # 缩短等待时间以加快检查
        logging.info(f"等待 {wait_time} 秒让 Docker 容器启动...")
        await asyncio.sleep(wait_time)
        logging.info("继续执行，尝试连接...")

        async with MCPClient(url) as mcp_client:
            logging.info(f"✅ 成功连接到 MCP 服务器: {url}")
            
            tool_summaries = await mcp_client.list_tools()
            if not tool_summaries:
                logging.error("🚨 无法从 MCP 服务器获取任何工具。")
                return
            
            logging.info(f"从服务器获取到 {len(tool_summaries)} 个工具。")
            
            # --- 核心检查逻辑 ---
            print("\n\n--- 🕵️  开始检查第一个工具对象的结构 🕵️  ---")
            first_tool = tool_summaries[0]
            
            print(f"\n[1] 对象的类型:")
            print(f"    {type(first_tool)}")
            
            print(f"\n[2] 对象的所有可用属性 (使用 dir()):")
            attributes = dir(first_tool)
            print(f"    {attributes}")
            
            print(f"\n[3] 逐一打印每个属性的值:")
            for attr in attributes:
                # 忽略内置的 dunder 方法以保持清晰
                if not attr.startswith('__'):
                    try:
                        value = getattr(first_tool, attr)
                        # 使用 repr() 来清晰地显示值的类型 (例如，字符串会带引号)
                        print(f"    - .{attr}  =>  {repr(value)}")
                    except Exception as e:
                        print(f"    - .{attr}  =>  <无法获取值: {e}>")
            
            print("\n--- ✅ 检查完成 ---")
            print("请将以上从 '--- 🕵️' 开始的全部输出内容复制并回复给我。")


    except Exception as e:
        logging.error(f"🚨 发生严重错误: {e}")
    finally:
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