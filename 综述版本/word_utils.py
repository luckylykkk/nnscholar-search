from docx.shared import Pt
from docx.oxml.ns import qn

def set_run_font(run, is_chinese=False):
    """设置run的字体
    
    Args:
        run: docx run对象
        is_chinese (bool): 是否是中文文本
    """
    font = run.font
    if is_chinese:
        # 中文使用宋体
        font.name = '宋体'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    else:
        # 英文使用Times New Roman
        font.name = 'Times New Roman'
    font.size = Pt(10.5)  # 设置字号为五号

def is_chinese_text(text):
    """判断文本是否包含中文字符
    
    Args:
        text (str): 要判断的文本
        
    Returns:
        bool: 是否包含中文字符
    """
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def add_paragraph_with_mixed_fonts(doc, text, is_bold=False, alignment=None):
    """添加包含中英文的段落，自动设置不同字体
    
    Args:
        doc: docx文档对象
        text (str): 要添加的文本
        is_bold (bool): 是否加粗
        alignment: 对齐方式
    
    Returns:
        paragraph: 添加的段落对象
    """
    p = doc.add_paragraph()
    if alignment:
        p.alignment = alignment
    
    # 分割文本为中文和英文部分
    current_text = ""
    current_is_chinese = None
    
    for char in text:
        is_char_chinese = '\u4e00' <= char <= '\u9fff'
        
        # 如果字符类型改变，或者是最后一个字符
        if current_is_chinese is not None and is_char_chinese != current_is_chinese:
            # 添加当前积累的文本
            run = p.add_run(current_text)
            run.bold = is_bold
            set_run_font(run, current_is_chinese)
            current_text = ""
        
        current_text += char
        current_is_chinese = is_char_chinese
    
    # 添加最后一部分文本
    if current_text:
        run = p.add_run(current_text)
        run.bold = is_bold
        set_run_font(run, current_is_chinese)
    
    return p 