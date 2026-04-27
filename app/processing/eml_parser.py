import email
import html
from email.policy import default as default_policy
from email.utils import getaddresses
import logging
import re
from pathlib import Path
from typing import Optional

from app.models import Attachment

logger = logging.getLogger(__name__)


def parse_eml_file(file_path: str) -> dict:
    """
    Parse a single .eml file and extract headers, body text, and attachments.
    Returns dict with keys: from_address, from_name, to_addresses, to_names,
    cc_addresses, bcc_addresses, subject, body_text, attachments, error
    """
    result = {
        "from_address": None,
        "from_name": None,
        "to_addresses": [],
        "to_names": [],
        "cc_addresses": [],
        "bcc_addresses": [],
        "subject": "",
        "body_text": "",
        "attachments": [],
        "error": None,
    }

    try:
        with open(file_path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=default_policy)
    except Exception as e:
        logger.error(f"Failed to parse EML file {file_path}: {e}")
        result["error"] = str(e)
        return result

    try:
        # Extract headers
        from_data = _parse_address_header_with_name(msg.get("From", ""))
        result["from_address"] = from_data[0]
        result["from_name"] = from_data[1]

        to_data = _parse_address_list_with_names(msg.get("To", ""))
        result["to_addresses"] = [addr for addr, _ in to_data]
        result["to_names"] = [name for _, name in to_data]

        result["cc_addresses"] = _parse_address_list(msg.get("CC", ""))
        result["bcc_addresses"] = _parse_address_list(msg.get("BCC", ""))
        result["subject"] = msg.get("Subject", "").strip()

        # Extract body text
        result["body_text"] = _extract_body_text(msg)

        # Extract attachments
        result["attachments"] = _extract_attachments(msg, Path(file_path).name)

    except Exception as e:
        logger.error(f"Error processing EML headers/content: {e}")
        result["error"] = str(e)

    return result


def _parse_address_header(addr_header: str) -> str:
    """Extract primary email address from From header"""
    if not addr_header:
        return None
    addresses = getaddresses([addr_header])
    if addresses and addresses[0][1]:
        return addresses[0][1].strip()
    return None


def _parse_address_header_with_name(addr_header: str) -> tuple[Optional[str], Optional[str]]:
    """Extract email address and display name from From header"""
    if not addr_header:
        return None, None
    addresses = getaddresses([addr_header])
    if addresses and addresses[0][1]:
        name = addresses[0][0].strip() if addresses[0][0] else None
        email = addresses[0][1].strip()
        return email, name
    return None, None


def _parse_address_list_with_names(addr_header: str) -> list[tuple[str, Optional[str]]]:
    """Extract list of (email, name) tuples from To/CC/BCC header"""
    if not addr_header:
        return []
    addresses = getaddresses([addr_header])
    return [(addr[1].strip(), addr[0].strip() if addr[0] else None) for addr in addresses if addr[1]]


def _parse_address_list(addr_header: str) -> list[str]:
    """Extract list of email addresses from To/CC/BCC header"""
    if not addr_header:
        return []
    addresses = getaddresses([addr_header])
    return [addr[1].strip() for addr in addresses if addr[1]]


def _extract_body_text(msg) -> str:
    """Extract body text from email message, preferring plain text"""
    text_parts = _collect_body_parts(msg, preferred_type="text/plain")
    if text_parts:
        return "\n".join(text_parts)

    html_parts = _collect_body_parts(msg, preferred_type="text/html")
    return "\n".join(html_parts)


def _collect_body_parts(part, preferred_type: str) -> list[str]:
    disposition = (part.get("Content-Disposition") or "").lower()
    if "attachment" in disposition:
        return []

    if part.is_multipart():
        collected = []
        for subpart in part.iter_parts():
            collected.extend(_collect_body_parts(subpart, preferred_type))
        return collected

    if part.get_content_type() != preferred_type:
        return []

    try:
        payload = part.get_payload(decode=True)
        if not payload:
            return []
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="ignore")
        if preferred_type == "text/html":
            text = _html_to_text(text)
        return [text]
    except Exception as e:
        logger.debug(f"Failed to decode {preferred_type} part: {e}")
        return []


def _html_to_text(html_content: str) -> str:
    html_content = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_content)
    html_content = re.sub(r"(?i)<br\s*/?>", "\n", html_content)
    html_content = re.sub(r"(?i)</(p|div|li|tr|h1|h2|h3|h4|h5|h6)>", "\n", html_content)
    html_content = re.sub(r"(?i)<(p|div|li|tr|table|ul|ol|h1|h2|h3|h4|h5|h6)[^>]*>", "\n", html_content)
    text = re.sub(r"<[^>]+>", " ", html_content)
    text = html.unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _extract_attachments(msg, eml_filename: str) -> list[Attachment]:
    """Extract all attachments from email message"""
    attachments = []

    for part in msg.walk():
        # Skip multipart containers and body parts
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue

        try:
            filename = part.get_filename()
            if not filename:
                continue

            # Decode RFC 2047 encoded filename if necessary
            try:
                filename = email.header.decode_header(filename)[0][0]
                if isinstance(filename, bytes):
                    filename = filename.decode("utf-8", errors="ignore")
            except Exception:
                pass

            mime_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload and mime_type == "message/rfc822":
                nested_payload = part.get_payload()
                if isinstance(nested_payload, list) and nested_payload:
                    payload = nested_payload[0].as_bytes()
                elif hasattr(nested_payload, "as_bytes"):
                    payload = nested_payload.as_bytes()
            if not payload:
                continue

            attachment = Attachment(
                filename=filename,
                mime_type=mime_type,
                data=payload,
                source_eml=eml_filename,
            )
            attachments.append(attachment)

        except Exception as e:
            logger.warning(f"Failed to extract attachment from {eml_filename}: {e}")
            continue

    return attachments
