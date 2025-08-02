import asyncio
import logging
from browser_agent import BrowserAgent

# 文件/模块/函数头部注释
# 核心功能: 演示如何使用 BrowserAgent 类来执行一个网页自动化任务。
# 作者: Your Name
# 日期: 2025-08-02

async def main():
    """
    这是一个如何使用 BrowserAgent 库的示例主函数。
    """
    print("--- 浏览器代理使用示例 ---")

    # 1. 创建代理实例
    agent = BrowserAgent()

    try:
        # 2. 异步初始化代理 (这个步骤会加载配置和模型，只需要执行一次)
        # 它会启动一个临时的 Docker 容器来获取工具定义，然后关闭它。
        await agent.initialize()

        # 3. 定义一个要执行的任务
        # 这是您的“项目 A”在搜索到 URL 后，想要执行的操作
        task_prompt = "请访问这个页面 https://www.nhk.or.jp/shutoken-news/20250730/1000120241.html 并总结其主要内容。"

        print(f"\n[任务]: {task_prompt}")
        print("\n[代理开始工作]...\n")

        # 4. 运行任务并等待结果
        # 这个方法会启动一个新的 Docker 容器来执行任务，并在任务结束后自动清理。
        final_result = await agent.run_task(task_prompt)

        # 5. 打印最终结果
        print("\n--- ✅ 任务完成 ---")
        print("[最终总结]:")
        print(final_result)
        print("--------------------")

    except RuntimeError as e:
        # 捕获我们在库中定义的特定错误
        logging.error(f"代理执行时发生运行时错误: {e}")
        print(f"\n--- ❌ 任务执行失败 ---")
        print(f"错误: {e}")
        print("------------------------")
    except Exception as e:
        # 捕获其他所有未知错误
        logging.error(f"发生未知错误: {e}")
        print(f"\n--- ❌ 任务执行失败 ---")
        print(f"发生未知错误: {e}")
        print("------------------------")


if __name__ == "__main__":
    # 确保在主入口点捕获 KeyboardInterrupt 以实现优雅退出
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断。")