import fastmcp
import importlib

# 这是一个安全的诊断脚本，用于检查您环境中 fastmcp 库的实际内容

print("--- 正在检查 'fastmcp' 库的内部结构 ---")

try:
    # 尝试获取已安装包的版本，这可能是关键信息
    from importlib.metadata import version
    pkg_version = version('fastmcp')
    print(f"\n[INFO] fastmcp 版本: {pkg_version}\n")
except ImportError:
    print("\n[INFO] 无法自动检测 fastmcp 版本。\n")


print("--- 1. 'fastmcp' 顶层可用的名称 ---")
# 列出可以直接从 'fastmcp' 导入的所有非私有名称
top_level_contents = [item for item in dir(fastmcp) if not item.startswith('_')]
print(top_level_contents)


print("\n--- 2. 尝试探测已知的子模块 ---")
# 我们将安全地测试之前失败过的所有子模块路径
submodules_to_test = ['subprocess', 'stdio', 'transports']
for module_name in submodules_to_test:
    try:
        # 使用 importlib 来安全地探测模块是否存在
        importlib.import_module(f"fastmcp.{module_name}")
        print(f"✅ 存在: 'fastmcp.{module_name}'")
    except ImportError:
        print(f"❌ 不存在: 'fastmcp.{module_name}'")


print("\n--- 检查完成 ---")
print("请将以上所有输出完整地复制并回复给我。")