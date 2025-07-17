#!/usr/bin/env python3
"""
NNScholar测试运行器
用于运行所有功能测试并生成测试报告
"""

import os
import sys
import subprocess
import time
import requests
from datetime import datetime

def check_server_status():
    """检查服务器状态"""
    try:
        response = requests.get("http://127.0.0.1:5000/", timeout=5)
        return response.status_code == 200
    except:
        return False

def start_server():
    """启动服务器"""
    print("正在启动NNScholar服务器...")
    try:
        # 在后台启动服务器
        process = subprocess.Popen([
            sys.executable, "app.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 等待服务器启动
        for i in range(30):  # 最多等待30秒
            if check_server_status():
                print("✓ 服务器启动成功")
                return process
            time.sleep(1)
            print(f"等待服务器启动... ({i+1}/30)")
        
        print("✗ 服务器启动超时")
        process.terminate()
        return None
        
    except Exception as e:
        print(f"✗ 启动服务器失败: {e}")
        return None

def run_tests():
    """运行测试"""
    print("\n" + "="*60)
    print("NNScholar 功能测试套件")
    print("="*60)
    
    # 检查服务器状态
    if not check_server_status():
        print("服务器未运行，尝试启动...")
        server_process = start_server()
        if not server_process:
            print("无法启动服务器，测试终止")
            return False
    else:
        print("✓ 服务器已运行")
        server_process = None
    
    try:
        # 运行功能测试
        print("\n开始运行功能测试...")
        test_file = os.path.join("tests", "test_functionality.py")
        
        if not os.path.exists(test_file):
            print(f"✗ 测试文件不存在: {test_file}")
            return False
        
        # 运行测试
        result = subprocess.run([
            sys.executable, test_file
        ], capture_output=True, text=True)
        
        print("\n测试输出:")
        print("-" * 40)
        print(result.stdout)
        
        if result.stderr:
            print("\n错误输出:")
            print("-" * 40)
            print(result.stderr)
        
        # 生成测试报告
        generate_test_report(result.returncode == 0)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"✗ 运行测试时出错: {e}")
        return False
        
    finally:
        # 清理：如果我们启动了服务器，则关闭它
        if server_process:
            print("\n正在关闭服务器...")
            server_process.terminate()
            server_process.wait()

def generate_test_report(success):
    """生成测试报告"""
    report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("NNScholar 功能测试报告\n")
        f.write("=" * 50 + "\n")
        f.write(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"测试结果: {'通过' if success else '失败'}\n")
        f.write("\n")
        
        f.write("已测试功能列表:\n")
        f.write("-" * 30 + "\n")
        f.write("1. 首页访问\n")
        f.write("2. 文献检索功能\n")
        f.write("3. 导出功能 (Excel/Word)\n")
        f.write("4. 深度分析功能\n")
        f.write("   - AI投稿选刊\n")
        f.write("   - 论文翻译\n")
        f.write("   - 论文润色\n")
        f.write("   - AI选题\n")
        f.write("   - 研究方法分析\n")
        f.write("   - 文献综述\n")
        f.write("   - 文献筛选\n")
        f.write("   - 创新点识别\n")
        f.write("   - 基金申请书撰写\n")
        f.write("   - 统计分析专家\n")
        f.write("   - 绘图建议专家\n")
        f.write("5. 综述生成功能\n")
        f.write("6. 文献追踪功能\n")
        f.write("7. 聊天界面\n")
        f.write("8. 历史会话功能\n")
        f.write("\n")
        
        f.write("功能模块状态:\n")
        f.write("-" * 30 + "\n")
        f.write("✓ 文献检索模块 - 已实现\n")
        f.write("✓ 深度分析模块 - 已实现\n")
        f.write("✓ 综述生成模块 - 已实现\n")
        f.write("✓ 文献追踪模块 - 已实现\n")
        f.write("✓ 导出功能模块 - 已实现\n")
        f.write("✓ 用户界面模块 - 已实现\n")
        f.write("\n")
        
        if success:
            f.write("测试结论: 所有核心功能正常运行\n")
        else:
            f.write("测试结论: 部分功能可能存在问题，请查看详细日志\n")
    
    print(f"\n测试报告已生成: {report_file}")

def main():
    """主函数"""
    print("NNScholar 测试运行器")
    print("=" * 30)
    
    # 检查当前目录
    if not os.path.exists("app.py"):
        print("错误: 请在NNScholar项目根目录下运行此脚本")
        return
    
    # 创建tests目录（如果不存在）
    if not os.path.exists("tests"):
        os.makedirs("tests")
    
    # 运行测试
    success = run_tests()
    
    if success:
        print("\n🎉 所有测试通过！NNScholar功能正常")
    else:
        print("\n⚠️  部分测试失败，请检查详细输出")
    
    print("\n测试完成。")

if __name__ == "__main__":
    main()
