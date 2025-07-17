"""File and directory utilities."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def ensure_directory(directory_path: str) -> bool:
    """Ensure directory exists, create if necessary.
    
    Args:
        directory_path: Path to directory
    
    Returns:
        True if directory exists or was created successfully
    """
    try:
        os.makedirs(directory_path, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {directory_path}: {e}")
        return False


def cleanup_temp_files(directory: str, max_age_hours: int = 24) -> int:
    """Clean up temporary files older than specified age.
    
    Args:
        directory: Directory to clean
        max_age_hours: Maximum age of files in hours
    
    Returns:
        Number of files cleaned up
    """
    if not os.path.exists(directory):
        return 0
    
    cleaned_count = 0
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    
    try:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            
            if os.path.isfile(file_path):
                # Get file modification time
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                if file_time < cutoff_time:
                    try:
                        os.remove(file_path)
                        cleaned_count += 1
                        logger.debug(f"Cleaned up old file: {filename}")
                    except Exception as e:
                        logger.warning(f"Failed to remove file {filename}: {e}")
    
    except Exception as e:
        logger.error(f"Error during cleanup of {directory}: {e}")
    
    if cleaned_count > 0:
        logger.info(f"Cleaned up {cleaned_count} old files from {directory}")
    
    return cleaned_count


def get_safe_filename(filename: str, max_length: int = 255) -> str:
    """Generate a safe filename by removing/replacing invalid characters.
    
    Args:
        filename: Original filename
        max_length: Maximum filename length
    
    Returns:
        Safe filename
    """
    if not filename:
        return "unnamed_file"
    
    # Remove or replace invalid characters
    import re
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
    safe_name = re.sub(r'[\x00-\x1f]', '', safe_name)  # Remove control characters
    safe_name = safe_name.strip('. ')  # Remove leading/trailing dots and spaces
    
    # Ensure not empty
    if not safe_name:
        safe_name = "unnamed_file"
    
    # Truncate if too long
    if len(safe_name) > max_length:
        name_part, ext_part = os.path.splitext(safe_name)
        available_length = max_length - len(ext_part)
        safe_name = name_part[:available_length] + ext_part
    
    return safe_name


def create_temp_file(suffix: str = None, prefix: str = None, 
                    directory: str = None) -> str:
    """Create a temporary file and return its path.
    
    Args:
        suffix: File suffix/extension
        prefix: File prefix
        directory: Directory for temp file
    
    Returns:
        Path to temporary file
    """
    try:
        fd, temp_path = tempfile.mkstemp(
            suffix=suffix,
            prefix=prefix,
            dir=directory
        )
        os.close(fd)  # Close file descriptor
        return temp_path
    except Exception as e:
        logger.error(f"Failed to create temporary file: {e}")
        raise


def get_file_size_mb(file_path: str) -> float:
    """Get file size in megabytes.
    
    Args:
        file_path: Path to file
    
    Returns:
        File size in MB
    """
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except Exception as e:
        logger.error(f"Failed to get size of {file_path}: {e}")
        return 0.0


def copy_file_safe(source: str, destination: str) -> bool:
    """Safely copy file with error handling.
    
    Args:
        source: Source file path
        destination: Destination file path
    
    Returns:
        True if copy was successful
    """
    try:
        # Ensure destination directory exists
        dest_dir = os.path.dirname(destination)
        ensure_directory(dest_dir)
        
        # Copy file
        shutil.copy2(source, destination)
        logger.debug(f"Copied {source} to {destination}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to copy {source} to {destination}: {e}")
        return False


def move_file_safe(source: str, destination: str) -> bool:
    """Safely move file with error handling.
    
    Args:
        source: Source file path
        destination: Destination file path
    
    Returns:
        True if move was successful
    """
    try:
        # Ensure destination directory exists
        dest_dir = os.path.dirname(destination)
        ensure_directory(dest_dir)
        
        # Move file
        shutil.move(source, destination)
        logger.debug(f"Moved {source} to {destination}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to move {source} to {destination}: {e}")
        return False


def delete_file_safe(file_path: str) -> bool:
    """Safely delete file with error handling.
    
    Args:
        file_path: Path to file to delete
    
    Returns:
        True if deletion was successful
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Deleted file: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete {file_path}: {e}")
        return False


def get_directory_size_mb(directory: str) -> float:
    """Get total size of directory in megabytes.
    
    Args:
        directory: Directory path
    
    Returns:
        Total size in MB
    """
    total_size = 0
    
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(file_path)
                except (OSError, FileNotFoundError):
                    pass  # Skip files that can't be accessed
    
    except Exception as e:
        logger.error(f"Error calculating directory size for {directory}: {e}")
    
    return total_size / (1024 * 1024)


def find_files_by_extension(directory: str, extensions: List[str], 
                           recursive: bool = True) -> List[str]:
    """Find files with specific extensions in directory.
    
    Args:
        directory: Directory to search
        extensions: List of file extensions (with or without dots)
        recursive: Whether to search recursively
    
    Returns:
        List of matching file paths
    """
    if not os.path.exists(directory):
        return []
    
    # Normalize extensions
    normalized_exts = []
    for ext in extensions:
        if not ext.startswith('.'):
            ext = '.' + ext
        normalized_exts.append(ext.lower())
    
    matching_files = []
    
    try:
        if recursive:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_ext = os.path.splitext(file)[1].lower()
                    if file_ext in normalized_exts:
                        matching_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    file_ext = os.path.splitext(file)[1].lower()
                    if file_ext in normalized_exts:
                        matching_files.append(file_path)
    
    except Exception as e:
        logger.error(f"Error finding files in {directory}: {e}")
    
    return matching_files


def is_file_accessible(file_path: str) -> bool:
    """Check if file exists and is accessible.
    
    Args:
        file_path: Path to file
    
    Returns:
        True if file is accessible
    """
    try:
        return os.path.isfile(file_path) and os.access(file_path, os.R_OK)
    except Exception:
        return False


def get_file_info(file_path: str) -> dict:
    """Get comprehensive file information.
    
    Args:
        file_path: Path to file
    
    Returns:
        Dictionary with file information
    """
    info = {
        'exists': False,
        'size_mb': 0.0,
        'created': None,
        'modified': None,
        'extension': '',
        'readable': False,
        'writable': False
    }
    
    try:
        if os.path.exists(file_path):
            info['exists'] = True
            
            stat = os.stat(file_path)
            info['size_mb'] = stat.st_size / (1024 * 1024)
            info['created'] = datetime.fromtimestamp(stat.st_ctime)
            info['modified'] = datetime.fromtimestamp(stat.st_mtime)
            info['extension'] = os.path.splitext(file_path)[1]
            info['readable'] = os.access(file_path, os.R_OK)
            info['writable'] = os.access(file_path, os.W_OK)
    
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}")
    
    return info