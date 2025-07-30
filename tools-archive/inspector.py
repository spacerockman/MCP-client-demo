import fastmcp
import importlib

print("--- 正在检查 'fastmcp' 库的内部结构 ---")

try:
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
submodules_to_test = ['subprocess', 'stdio', 'transports']
for module_name in submodules_to_test:
    try:
        # 使用 importlib 来安全地探测模块是否存在
        importlib.import_module(f"fastmcp.{module_name}")
        print(f"✅ 存在: 'fastmcp.{module_name}'")
    except ImportError:
        print(f"❌ 不存在: 'fastmcp.{module_name}'")