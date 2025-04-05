import re
import os
from .constants import MAX_FILENAME_LEN

def sanitize_filename(filename: str) -> str:
    """Removes characters potentially problematic for filenames.

    The function removes or replaces problematic characters, replaces
    multiple consecutive hyphens with a single one, removes leading/trailing
    hyphens and whitespace, and limits the length of the filename by
    shortening the name part if necessary.
    """
    # Remove or replace characters like :, /, \, ?, *, <, >, |
    sanitized = re.sub(r'[:/\\?*<>|]', '-', filename) # Corrected regex escape
    # Replace multiple consecutive hyphens with a single one
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remove leading/trailing hyphens and whitespace
    sanitized = sanitized.strip(' -')
    # Limit length
    if len(sanitized) > MAX_FILENAME_LEN:
        name, ext = os.path.splitext(sanitized)
        # Ensure extension is not overly long itself, though unlikely
        if len(ext) > MAX_FILENAME_LEN / 2:
             ext = ext[:int(MAX_FILENAME_LEN / 2)] # Truncate long extension
        sanitized = name[:MAX_FILENAME_LEN - len(ext)] + ext
    return sanitized
