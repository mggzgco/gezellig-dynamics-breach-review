"""Core analysis pipeline components.

Broad flow:
- parse emails and attachments
- detect PII candidates and score findings
- attribute findings to entities
- run file-level QA and risk scoring
- hand normalized results to reporting
"""
