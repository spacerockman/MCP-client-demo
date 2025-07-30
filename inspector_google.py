import google.generativeai as genai
import importlib.metadata

# 这是一个安全的诊断脚本，用于检查您环境中 google-generativeai 库的实际内容

print("--- 正在检查 'google-generativeai' 库的内部结构 ---")

try:
    # 获取已安装包的版本，这是解决问题的最关键信息
    pkg_version = importlib.metadata.version('google-generativeai')
    print(f"\n[INFO] google-generativeai 版本: {pkg_version}\n")
except importlib.metadata.PackageNotFoundError:
    print("\n[INFO] 无法自动检测 google-generativeai 版本。\n")


print("--- 1. 'google.generativeai' 顶层可用的名称 ---")
# 列出可以直接从 'genai' 访问的所有非私有名称
top_level_contents = [item for item in dir(genai) if not item.startswith('_')]
print(top_level_contents)


print("\n--- 2. 'google.generativeai.types' 子模块可用的名称 ---")
# 列出可以直接从 'genai.types' 访问的所有非私有名称
try:
    types_contents = [item for item in dir(genai.types) if not item.startswith('_')]
    print(types_contents)
except Exception as e:
    print(f"无法检查 'genai.types' 的内容: {e}")


print("\n--- 检查完成 ---")
print("请将以上所有输出完整地复制并回复给我。")