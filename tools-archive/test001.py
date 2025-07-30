# from mcp.client.session import ClientSession  <- 不再需要这个
# from mcp.client import connect              <- 这是另一种方式
from fastmcp import Client  # <--- 推荐使用这个高级客户端类
import asyncio

async def main():
    # Client 类会自动推断连接方式（本地脚本、HTTP等）
    # 它会为您处理所有底层的流和会话管理
    async with Client("http://localhost:8931/mcp") as client:
        try:
            print("Pinging server...")
            await client.ping()
            print("Server is responsive.")

            # List what's available
            print("\nListing available tools...")
            tools = await client.list_tools()
            print(f"--> Tools found: {tools}")

            # Use tools
            print("\nCalling tool 'search_flights'...")
            flights = await client.call_tool("search_flights", {
                "origin": "SFO",
                "destination": "JFK"
            })
            print(f"--> Flight search result: {flights}")

            # Read resources
            print("\nReading resource 'flight://status/UA123'...")
            status = await client.read_resource("flight://status/UA123")
            print(f"--> Resource status: {status}")

            # Get prompts
            print("\nGetting prompt 'find_flight'...")
            advice = await client.get_prompt("find_flight", {
                "details": "SFO to JFK"
            })
            print(f"--> Prompt advice: {advice}")

        except Exception as e:
            print(f"\nAn error occurred during interaction: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        # 捕获连接阶段的错误
        print(f"Failed to connect or run client: {e}")