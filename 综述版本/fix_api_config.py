import re

def fix_api_config_calls():
    # 读取app.py文件
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 保存原始内容的备份
    with open('app.py.bak2', 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 定义正则表达式模式来匹配get_api_config()调用，但排除已经有log_info参数的调用
    pattern = r'api_config\s*=\s*get_api_config\(\)'
    
    # 替换为带有log_info=False参数的调用
    replacement = r'api_config = get_api_config(log_info=False)'
    
    # 进行替换
    new_content = re.sub(pattern, replacement, content)
    
    # 保存修改后的内容
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("已完成所有get_api_config()调用的修改")

if __name__ == "__main__":
    fix_api_config_calls() 