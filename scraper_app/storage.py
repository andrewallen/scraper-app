"""Handles file system operations like filename generation and file downloading."""

import os
import logging
import re
import requests
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, Tuple

from .utils import sanitize_filename
from .constants import DOWNLOAD_TIMEOUT

def generate_filename(url: str, output_dir: str, date_prefix: Optional[str] = None, file_extension: str = ".md") -> Tuple[str, str]:
    """Generates a safe, domain-specific filename and the full path.

    Args:
        url: The source URL.
        output_dir: The base output directory.
        date_prefix: Optional date string (YYYY-MM-DD) to prepend.
        file_extension: The file extension (e.g., '.md', '.pdf').

    Returns:
        A tuple containing (domain_output_directory, full_filepath).
    """
    parsed_url = urlparse(url)
    domain_name = parsed_url.netloc or "unknown_domain"

    # Generate base filename from path or domain
    path_parts = [part for part in parsed_url.path.strip('/').split('/') if part]
    if not path_parts:
        # If path is empty or just '/', use domain name
        base_filename = domain_name.replace('.', '_')
    else:
        # Use the last part of the path if available, otherwise join all
        base_filename = path_parts[-1] if path_parts[-1] else '_'.join(path_parts)
        if not base_filename: # Fallback if path parsing yields nothing useful
            base_filename = domain_name.replace('.', '_')

    # Add original extension if it looks like a file path, otherwise use provided extension
    # Check if the last part seems to have an extension (e.g., .pdf, .html)
    _, potential_ext = os.path.splitext(base_filename)
    if potential_ext and len(potential_ext) > 1 and len(potential_ext) <= 5: # Basic check
        # If the url path already has a file-like extension, use it as the base
        # unless we are specifically saving as markdown
        if file_extension == ".md":
            name_part, _ = os.path.splitext(base_filename)
            filename = name_part + file_extension
        else:
            # Keep the original filename if we're not saving as markdown
            filename = base_filename
    elif file_extension and not base_filename.endswith(file_extension):
        # Append the desired extension if it's missing
        filename = base_filename + file_extension
    else:
        filename = base_filename # Use base as is

    # Sanitize the filename part
    filename = sanitize_filename(filename)

    # Prepend date if available
    if date_prefix:
        filename = f"{date_prefix}_{filename}"

    # Ensure domain directory exists
    domain_output_dir = os.path.join(output_dir, domain_name)
    os.makedirs(domain_output_dir, exist_ok=True)

    filepath = os.path.join(domain_output_dir, filename)
    return domain_output_dir, filepath

def download_binary_file(url: str, output_dir: str, user_agent: str) -> Optional[str]:
    """Downloads a binary file from a URL and saves it.

    Args:
        url (str): The URL of the binary file.
        output_dir (str): The base directory to save the file.
        user_agent (str): The User-Agent string for the request.

    Returns:
        str: The full path of the saved file if successful, None otherwise.
    """
    headers = {'User-Agent': user_agent}
    filepath: Optional[str] = None # Initialize filepath
    formatted_date_prefix: Optional[str] = None

    try:
        logging.debug(f"Attempting to download binary file: {url}")
        response = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status() # Check for HTTP errors

        # Determine filename from Content-Disposition header first, then URL path
        content_disposition = response.headers.get('content-disposition')
        filename_from_header = None
        if content_disposition:
            # Simple parsing, might need refinement for complex cases
            parts = content_disposition.split('filename=')
            if len(parts) > 1:
                filename_from_header = parts[1].strip('\"\' ')

        # Determine date prefix from URL path (optional)
        parsed_url = urlparse(url)
        date_match = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', parsed_url.path)
        if date_match:
            year_str, month_str, day_str = date_match.groups()
            try:
                # Pad month/day if needed for strptime
                file_date = datetime.strptime(f"{year_str}-{int(month_str):02d}-{int(day_str):02d}", '%Y-%m-%d')
                formatted_date_prefix = file_date.strftime('%Y-%m-%d')
            except ValueError:
                logging.warning(f"Invalid date {year_str}-{month_str}-{day_str} in binary URL path {parsed_url.path}, skipping date prefix.")

        # Determine file extension from Content-Type or URL
        content_type = response.headers.get('content-type', '').split(';')[0].lower()
        extension = None
        # Prefer extension from header filename if available
        if filename_from_header and '.' in filename_from_header:
            _, extension = os.path.splitext(filename_from_header)
        # Fallback to URL path extension
        elif '.' in os.path.basename(parsed_url.path):
            _, extension = os.path.splitext(os.path.basename(parsed_url.path))
        # Fallback to Content-Type mapping
        elif content_type == 'application/pdf':
            extension = '.pdf'
        elif content_type == 'application/msword':
            extension = '.doc'
        elif content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            extension = '.docx'
        elif content_type == 'application/vnd.ms-excel':
            extension = '.xls'
        elif content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            extension = '.xlsx'
        elif content_type == 'text/csv':
            extension = '.csv'
        # Add more common types as needed

        if not extension:
            logging.warning(f"Could not determine file extension for {url} (Content-Type: {content_type}). Using '.bin'")
            extension = '.bin'

        # Filename fallback order:
        # 1. Content-Disposition header
        # 2. Last path component of the URL
        # 3. Derived from Content-Type header (e.g., document.pdf)
        # 4. Default 'downloaded_file.bin'
        filename_from_cd = filename_from_header
        filename_from_url = os.path.basename(parsed_url.path)
        filename_from_type = f"downloaded_file{extension}"
        filename = filename_from_cd or filename_from_url or filename_from_type or "downloaded_file.bin"

        # Fallback: Try to extract date from URL path (common in blogs/news)
        # Assumes a /YYYY/MM/DD/ structure somewhere in the path.
        match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', parsed_url.path)
        if match:
            year_str, month_str, day_str = match.groups()
            try:
                # Pad month/day if needed for strptime
                file_date = datetime.strptime(f"{year_str}-{int(month_str):02d}-{int(day_str):02d}", '%Y-%m-%d')
                formatted_date_prefix = file_date.strftime('%Y-%m-%d')
            except ValueError:
                logging.warning(f"Invalid date {year_str}-{month_str}-{day_str} in binary URL path {parsed_url.path}, skipping date prefix.")

        # Generate filename using the consolidated function, passing the determined extension
        domain_dir, temp_filepath = generate_filename(url, output_dir, formatted_date_prefix, extension)

        # Override filename part if we got one from header (but keep generated path/date/domain)
        if filename_from_header:
            final_filename = sanitize_filename(filename_from_header)
            # Ensure the extension matches the sanitized header filename, if possible
            base_header, ext_header = os.path.splitext(final_filename)
            if not ext_header: # If sanitizing removed the extension, add it back
                final_filename += extension

            if formatted_date_prefix and not final_filename.startswith(formatted_date_prefix):
                final_filename = f"{formatted_date_prefix}_{final_filename}"
            filepath = os.path.join(domain_dir, final_filename)
        else:
            filepath = temp_filepath

        # Download and save
        logging.info(f"Downloading binary file from {url} to {filepath}")
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logging.info(f"Successfully downloaded and saved {url} to {filepath}")
        return filepath # Return the path on success

    except requests.exceptions.Timeout:
        logging.error(f"Timeout downloading binary file: {url}")
        return None
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error downloading binary file {url}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading binary file {url}: {e}")
        return None
    except IOError as e:
        # Check if filepath is assigned before logging
        log_filepath = filepath if filepath else "unknown path"
        logging.error(f"Error saving binary file {log_filepath}: {e}")
        return None
    except Exception as e: # Catch unexpected errors
        logging.error(f"Unexpected error processing binary file {url}: {e}")
        return None
