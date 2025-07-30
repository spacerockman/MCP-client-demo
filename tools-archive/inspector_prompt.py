import prompt_toolkit
import importlib.metadata

# 这是一个安全的诊断脚本，用于检查您环境中 prompt_toolkit 库的实际内容

print("--- 正在检查 'prompt_toolkit' 库的内部结构 ---")

try:
    # 获取已安装包的版本，这是解决问题的最关键信息
    pkg_version = importlib.metadata.version('prompt_toolkit')
    print(f"\n[INFO] prompt_toolkit 版本: {pkg_version}\n")
except importlib.metadata.PackageNotFoundError:
    print("\n[INFO] 无法自动检测 prompt_toolkit 版本。\n")


print("--- 'prompt_toolkit.shortcuts' 子模块可用的名称 ---")
try:
    import prompt_toolkit.shortcuts
    # 列出可以直接从 'prompt_toolkit.shortcuts' 访问的所有非私有名称
    shortcuts_contents = [item for item in dir(prompt_toolkit.shortcuts) if not item.startswith('_')]
    print(shortcuts_contents)

    # 明确检查 'prompt_async' 是否存在
    if 'prompt_async' in shortcuts_contents:
        print("\n[INFO] ✅ 'prompt_async' 存在于 shortcuts 模块中。")
    else:
        print("\n[INFO] ❌ 'prompt_async' 不存在于 shortcuts 模块中。")

except Exception as e:
    print(f"无法检查 'prompt_toolkit.shortcuts' 的内容: {e}")


print("\n--- 检查完成 ---")
print("请将以上所有输出完整地复制并回复给我。")