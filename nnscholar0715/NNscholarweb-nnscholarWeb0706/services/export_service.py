"""Export service for generating Excel and Word documents."""

import os
import io
from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime

# Excel/Word libraries
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE

from config.settings import config
from models.paper import PaperDetail
from models.journal import journal_db
from utils.file_utils import ensure_directory, create_temp_file, get_safe_filename
from utils.text_processing import format_citation

logger = logging.getLogger(__name__)


class ExportService:
    """Service for exporting papers to various formats."""
    
    def __init__(self):
        self.export_dir = config.EXPORTS_DIR
        ensure_directory(self.export_dir)
    
    def export_to_excel(self, papers: List[Dict[str, Any]], 
                       filename: Optional[str] = None,
                       include_metrics: bool = True) -> Tuple[str, str]:
        """Export papers to Excel format.
        
        Args:
            papers: List of paper information
            filename: Custom filename (optional)
            include_metrics: Whether to include journal metrics
        
        Returns:
            Tuple of (file_path, filename)
        """
        try:
            if not papers:
                raise ValueError("No papers to export")
            
            # Generate filename
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"papers_export_{timestamp}.xlsx"
            
            filename = get_safe_filename(filename)
            if not filename.endswith('.xlsx'):
                filename += '.xlsx'
            
            file_path = os.path.join(self.export_dir, filename)
            
            # Prepare data
            export_data = self._prepare_excel_data(papers, include_metrics)
            
            # Create Excel file
            self._create_excel_file(export_data, file_path)
            
            logger.info(f"Exported {len(papers)} papers to Excel: {filename}")
            
            return file_path, filename
            
        except Exception as e:
            logger.error(f"Excel export failed: {e}")
            raise Exception(f"Excel export failed: {str(e)}")
    
    def export_to_word(self, papers: List[Dict[str, Any]], 
                      title: str = "Literature Review",
                      filename: Optional[str] = None,
                      include_abstracts: bool = True) -> Tuple[str, str]:
        """Export papers to Word format.
        
        Args:
            papers: List of paper information
            title: Document title
            filename: Custom filename (optional)
            include_abstracts: Whether to include abstracts
        
        Returns:
            Tuple of (file_path, filename)
        """
        try:
            if not papers:
                raise ValueError("No papers to export")
            
            # Generate filename
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"literature_review_{timestamp}.docx"
            
            filename = get_safe_filename(filename)
            if not filename.endswith('.docx'):
                filename += '.docx'
            
            file_path = os.path.join(self.export_dir, filename)
            
            # Create Word document
            self._create_word_document(papers, title, file_path, include_abstracts)
            
            logger.info(f"Exported {len(papers)} papers to Word: {filename}")
            
            return file_path, filename
            
        except Exception as e:
            logger.error(f"Word export failed: {e}")
            raise Exception(f"Word export failed: {str(e)}")
    
    def _prepare_excel_data(self, papers: List[Dict[str, Any]], 
                           include_metrics: bool) -> pd.DataFrame:
        """Prepare data for Excel export.
        
        Args:
            papers: List of paper information
            include_metrics: Whether to include journal metrics
        
        Returns:
            DataFrame with paper data
        """
        data_rows = []
        
        for i, paper in enumerate(papers, 1):
            # Basic information
            row = {
                '序号': i,
                'PMID': paper.get('pmid', ''),
                '标题': paper.get('title', ''),
                '作者': ', '.join(paper.get('authors', [])),
                '期刊': paper.get('journal', ''),
                '发表年份': paper.get('pub_date', '')[:4] if paper.get('pub_date') else '',
                'DOI': paper.get('doi', ''),
                '摘要': paper.get('abstract', ''),
                '关键词': ', '.join(paper.get('keywords', [])),
                'MeSH词汇': ', '.join(paper.get('mesh_terms', [])),
                '发表类型': ', '.join(paper.get('publication_types', [])),
                'URL': f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('pmid', '')}/" if paper.get('pmid') else ''
            }
            
            # Add relevance score if available
            if paper.get('relevance_score') is not None:
                row['相关性评分'] = f"{paper['relevance_score']:.3f}"
                row['相关性说明'] = paper.get('relevance_reason', '')
            
            # Add journal metrics if requested
            if include_metrics:
                journal_name = paper.get('journal', '')
                if journal_name:
                    metrics = journal_db.get_journal_metrics(journal_name)
                    if metrics:
                        row['影响因子'] = metrics.impact_factor or 'N/A'
                        row['5年影响因子'] = metrics.five_year_impact_factor or 'N/A'
                        row['JCR分区'] = metrics.jcr_quartile or 'N/A'
                        row['中科院分区'] = metrics.cas_quartile or 'N/A'
                        row['JCR学科'] = metrics.jcr_category or 'N/A'
                        row['中科院学科'] = metrics.cas_category or 'N/A'
                    else:
                        row['影响因子'] = 'N/A'
                        row['5年影响因子'] = 'N/A'
                        row['JCR分区'] = 'N/A'
                        row['中科院分区'] = 'N/A'
                        row['JCR学科'] = 'N/A'
                        row['中科院学科'] = 'N/A'
            
            data_rows.append(row)
        
        return pd.DataFrame(data_rows)
    
    def _create_excel_file(self, data: pd.DataFrame, file_path: str):
        """Create formatted Excel file.
        
        Args:
            data: DataFrame with paper data
            file_path: Output file path
        """
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "文献列表"
        
        # Add title
        ws.merge_cells('A1:L1')
        title_cell = ws['A1']
        title_cell.value = f"文献检索结果 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        title_cell.font = Font(name='微软雅黑', size=16, bold=True)
        title_cell.alignment = Alignment(horizontal='center', vertical='center')
        title_cell.fill = PatternFill(start_color='E8F4FD', end_color='E8F4FD', fill_type='solid')
        
        # Add summary
        ws.merge_cells('A2:L2')
        summary_cell = ws['A2']
        summary_cell.value = f"共检索到 {len(data)} 篇文献"
        summary_cell.font = Font(name='微软雅黑', size=12)
        summary_cell.alignment = Alignment(horizontal='center')
        
        # Add data starting from row 4
        start_row = 4
        
        # Add headers
        for col_num, column_name in enumerate(data.columns, 1):
            cell = ws.cell(row=start_row, column=col_num)
            cell.value = column_name
            cell.font = Font(name='微软雅黑', size=11, bold=True)
            cell.fill = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Add data rows
        for row_num, row_data in enumerate(data.itertuples(index=False), start_row + 1):
            for col_num, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = value
                cell.font = Font(name='微软雅黑', size=10)
                cell.alignment = Alignment(vertical='top', wrap_text=True)
        
        # Set column widths
        column_widths = {
            'A': 8,   # 序号
            'B': 12,  # PMID
            'C': 50,  # 标题
            'D': 30,  # 作者
            'E': 25,  # 期刊
            'F': 10,  # 年份
            'G': 20,  # DOI
            'H': 60,  # 摘要
            'I': 20,  # 关键词
            'J': 20,  # MeSH
            'K': 15,  # 发表类型
            'L': 30   # URL
        }
        
        for col, width in column_widths.items():
            ws.column_dimensions[col].width = width
        
        # Add borders
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        for row in ws[f'A{start_row}:L{start_row + len(data)}']:
            for cell in row:
                cell.border = thin_border
        
        # Save file
        wb.save(file_path)
    
    def _create_word_document(self, papers: List[Dict[str, Any]], 
                             title: str, file_path: str, 
                             include_abstracts: bool):
        """Create formatted Word document.
        
        Args:
            papers: List of paper information
            title: Document title
            file_path: Output file path
            include_abstracts: Whether to include abstracts
        """
        # Create document
        doc = Document()
        
        # Set document margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)
        
        # Add title
        title_para = doc.add_heading(title, level=1)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add summary
        summary_para = doc.add_paragraph()
        summary_para.add_run(f"检索日期：{datetime.now().strftime('%Y年%m月%d日')}\n")
        summary_para.add_run(f"文献数量：{len(papers)}篇\n\n")
        summary_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add papers
        for i, paper in enumerate(papers, 1):
            # Paper header
            header_para = doc.add_heading(f"{i}. {paper.get('title', 'No Title')}", level=2)
            header_para.paragraph_format.space_before = Pt(12)
            header_para.paragraph_format.space_after = Pt(6)
            
            # Basic information
            info_para = doc.add_paragraph()
            
            # Authors
            authors = paper.get('authors', [])
            if authors:
                author_text = ', '.join(authors[:5])  # Limit to first 5 authors
                if len(authors) > 5:
                    author_text += ', et al.'
                info_para.add_run(f"作者：{author_text}\n").bold = True
            
            # Journal and year
            journal = paper.get('journal', '')
            year = paper.get('pub_date', '')[:4] if paper.get('pub_date') else ''
            if journal:
                journal_text = f"期刊：{journal}"
                if year:
                    journal_text += f" ({year})"
                info_para.add_run(journal_text + "\n")
            
            # DOI and PMID
            pmid = paper.get('pmid', '')
            doi = paper.get('doi', '')
            if pmid:
                info_para.add_run(f"PMID：{pmid}\n")
            if doi:
                info_para.add_run(f"DOI：{doi}\n")
            
            # Journal metrics
            if journal:
                metrics = journal_db.get_journal_metrics(journal)
                if metrics:
                    metrics_text = []
                    if metrics.impact_factor:
                        metrics_text.append(f"影响因子：{metrics.impact_factor}")
                    if metrics.jcr_quartile:
                        metrics_text.append(f"JCR分区：{metrics.jcr_quartile}")
                    if metrics.cas_quartile:
                        metrics_text.append(f"中科院分区：{metrics.cas_quartile}")
                    
                    if metrics_text:
                        info_para.add_run("期刊指标：" + "，".join(metrics_text) + "\n")
            
            # Keywords
            keywords = paper.get('keywords', [])
            if keywords:
                keyword_text = '，'.join(keywords[:10])  # Limit keywords
                info_para.add_run(f"关键词：{keyword_text}\n")
            
            # Abstract
            if include_abstracts:
                abstract = paper.get('abstract', '')
                if abstract:
                    abstract_para = doc.add_paragraph()
                    abstract_para.add_run("摘要：").bold = True
                    abstract_para.add_run(abstract)
                    abstract_para.paragraph_format.left_indent = Inches(0.5)
                    abstract_para.paragraph_format.space_after = Pt(6)
            
            # URL
            if pmid:
                url_para = doc.add_paragraph()
                url_para.add_run(f"链接：https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
                url_para.paragraph_format.space_after = Pt(12)
            
            # Add separator
            if i < len(papers):
                separator_para = doc.add_paragraph()
                separator_para.add_run("—" * 50)
                separator_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                separator_para.paragraph_format.space_before = Pt(6)
                separator_para.paragraph_format.space_after = Pt(6)
        
        # Add footer
        footer_para = doc.add_paragraph()
        footer_para.add_run(f"\n\n生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
        footer_para.add_run("\n由NNScholar智能文献检索平台生成")
        footer_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        
        # Save document
        doc.save(file_path)
    
    def export_analysis_report(self, analysis_data: Dict[str, Any], 
                             filename: Optional[str] = None) -> Tuple[str, str]:
        """Export analysis report to Word format.
        
        Args:
            analysis_data: Analysis results
            filename: Custom filename (optional)
        
        Returns:
            Tuple of (file_path, filename)
        """
        try:
            # Generate filename
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"analysis_report_{timestamp}.docx"
            
            filename = get_safe_filename(filename)
            if not filename.endswith('.docx'):
                filename += '.docx'
            
            file_path = os.path.join(self.export_dir, filename)
            
            # Create document
            doc = Document()
            
            # Title
            title = analysis_data.get('title', '学术文献分析报告')
            doc.add_heading(title, level=1)
            
            # Summary
            if 'summary' in analysis_data:
                doc.add_heading('摘要', level=2)
                doc.add_paragraph(analysis_data['summary'])
            
            # Main content
            if 'content' in analysis_data:
                doc.add_heading('分析结果', level=2)
                doc.add_paragraph(analysis_data['content'])
            
            # Recommendations
            if 'recommendations' in analysis_data:
                doc.add_heading('建议', level=2)
                doc.add_paragraph(analysis_data['recommendations'])
            
            # Metadata
            doc.add_heading('生成信息', level=2)
            metadata_para = doc.add_paragraph()
            metadata_para.add_run(f"生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
            if 'paper_count' in analysis_data:
                metadata_para.add_run(f"分析文献数量：{analysis_data['paper_count']}篇\n")
            metadata_para.add_run("由NNScholar智能文献检索平台生成")
            
            doc.save(file_path)
            
            logger.info(f"Exported analysis report: {filename}")
            
            return file_path, filename
            
        except Exception as e:
            logger.error(f"Analysis report export failed: {e}")
            raise Exception(f"Analysis report export failed: {str(e)}")
    
    def create_bibliography(self, papers: List[Dict[str, Any]], 
                          style: str = 'apa',
                          filename: Optional[str] = None) -> Tuple[str, str]:
        """Create bibliography in specified citation style.
        
        Args:
            papers: List of paper information
            style: Citation style ('apa', 'mla', 'chicago')
            filename: Custom filename (optional)
        
        Returns:
            Tuple of (file_path, filename)
        """
        try:
            if not papers:
                raise ValueError("No papers to create bibliography")
            
            # Generate filename
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"bibliography_{style}_{timestamp}.docx"
            
            filename = get_safe_filename(filename)
            if not filename.endswith('.docx'):
                filename += '.docx'
            
            file_path = os.path.join(self.export_dir, filename)
            
            # Create document
            doc = Document()
            
            # Title
            doc.add_heading('参考文献', level=1)
            
            # Add citations
            for i, paper in enumerate(papers, 1):
                citation = self._format_citation(paper, style)
                if citation:
                    para = doc.add_paragraph()
                    para.add_run(f"{i}. {citation}")
                    para.paragraph_format.left_indent = Inches(0.5)
                    para.paragraph_format.first_line_indent = Inches(-0.5)
                    para.paragraph_format.space_after = Pt(6)
            
            doc.save(file_path)
            
            logger.info(f"Created bibliography with {len(papers)} citations: {filename}")
            
            return file_path, filename
            
        except Exception as e:
            logger.error(f"Bibliography creation failed: {e}")
            raise Exception(f"Bibliography creation failed: {str(e)}")
    
    def _format_citation(self, paper: Dict[str, Any], style: str) -> str:
        """Format citation according to style.
        
        Args:
            paper: Paper information
            style: Citation style
        
        Returns:
            Formatted citation
        """
        try:
            title = paper.get('title', '')
            authors = paper.get('authors', [])
            journal = paper.get('journal', '')
            year = paper.get('pub_date', '')[:4] if paper.get('pub_date') else ''
            pmid = paper.get('pmid', '')
            doi = paper.get('doi', '')
            
            return format_citation(title, authors, journal, year, pmid, doi)
            
        except Exception as e:
            logger.error(f"Citation formatting failed: {e}")
            return f"{paper.get('title', 'Unknown title')} - {paper.get('journal', 'Unknown journal')}"
    
    def get_export_statistics(self) -> Dict[str, Any]:
        """Get export directory statistics.
        
        Returns:
            Export statistics
        """
        try:
            if not os.path.exists(self.export_dir):
                return {"error": "Export directory does not exist"}
            
            files = os.listdir(self.export_dir)
            
            stats = {
                "total_files": len(files),
                "excel_files": len([f for f in files if f.endswith('.xlsx')]),
                "word_files": len([f for f in files if f.endswith('.docx')]),
                "export_directory": self.export_dir
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get export statistics: {e}")
            return {"error": str(e)}
    
    def cleanup_old_exports(self, max_age_hours: int = 24) -> int:
        """Clean up old export files.
        
        Args:
            max_age_hours: Maximum age of files to keep
        
        Returns:
            Number of files deleted
        """
        try:
            from utils.file_utils import cleanup_temp_files
            return cleanup_temp_files(self.export_dir, max_age_hours)
            
        except Exception as e:
            logger.error(f"Export cleanup failed: {e}")
            return 0


# Global service instance
export_service = ExportService()