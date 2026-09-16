"""Opt-in, standalone synthetic-diagnostic Secretary action proposals.

This module is not imported by the service, router or frozen evaluator. It does
not execute tools, load models, inspect file contents or decide task success.
A proposal needs independently validated execution and versioned quality/energy
measurement before any production integration.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

VERSION = 'secretary-explicit-proposal-diagnostic-v1'
_PATH = re.compile(r'[A-Za-z0-9_. /-]+\Z', re.ASCII)
_RESERVED = re.compile(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z', re.I)
_QUOTED = r'"([^"\\\r\n]+)"'
_PREFIX = r'(?:please )?'
_SUFFIX = r'\.?'


def safe_relative_path(path):
    """Conservative portable spelling only; not a substitute for realpath safety."""
    if not isinstance(path, str) or not path or len(path) > 240 or not _PATH.fullmatch(path):
        return False
    parts = path.split('/')
    return all(part not in ('', '.', '..') and part == part.strip() and not part.endswith('.')
               and not _RESERVED.fullmatch(part) for part in parts)


def propose(prompt, inventory, *, enabled=False):
    """Return a proposed tool action or abstain; enabled must explicitly be True.

    Grammar covers complete English imperative commands only, using double
    quotes for literal arguments. Unsupported paraphrases, clauses, ambiguity,
    negation outside literals and unfamiliar path spellings deliberately abstain.
    Inventory contains caller-supplied relative file names, never golden labels.
    """
    def abstain(reason):
        return dict(status='abstain', action=None, reason=reason, candidate_version=VERSION,
                    executed=False, quality_validated=False)
    if enabled is not True:
        return abstain('candidate disabled; explicit opt-in required')
    if not isinstance(prompt, str) or not prompt or len(prompt) > 2048 or any(ord(c) < 32 for c in prompt):
        return abstain('unsupported prompt shape')
    if not isinstance(inventory, (list, tuple)) or any(not safe_relative_path(p) for p in inventory):
        return abstain('inventory requires safe portable relative file names')
    if len(set(p.casefold() for p in inventory)) != len(inventory):
        return abstain('duplicate or case-ambiguous inventory')
    files = set(inventory)
    directories = {str(parent) for name in inventory for parent in PurePosixPath(name).parents}
    if {p.casefold() for p in files} & {p.casefold() for p in directories}:
        return abstain('inventory contains a file/directory collision')
    text = prompt.strip()
    def match(body):
        return re.fullmatch(_PREFIX + body + _SUFFIX, text, flags=re.I | re.ASCII)
    action = None
    if match(r'list (?:all files|every file|files)(?: in the workspace)?'):
        action = {'name': 'list_files', 'arguments': {}}
    elif found := match(r'read (?:the file )?' + _QUOTED):
        path = found.group(1)
        if not safe_relative_path(path) or path not in files:
            return abstain('read requires an exact existing inventory path')
        action = {'name': 'read_file', 'arguments': {'path': path}}
    elif found := match(r'move ' + _QUOTED + r' to ' + _QUOTED):
        source, destination = found.groups()
        if not safe_relative_path(source) or source not in files or not safe_relative_path(destination):
            return abstain('move requires safe paths and exact existing source')
        if destination.casefold() in {p.casefold() for p in files | directories}:
            return abstain('destination exists or is a known directory')
        if any(str(parent).casefold() in {p.casefold() for p in files}
               for parent in PurePosixPath(destination).parents):
            return abstain('destination parent is an existing file')
        # A quoted folder name and a filename without extension are ambiguous in
        # this deliberately narrow grammar; never infer or append a basename.
        if '.' not in PurePosixPath(destination).name:
            return abstain('destination must be an explicit filename with extension')
        action = {'name': 'move_file', 'arguments': {'path': source, 'destination': destination}}
    elif found := match(r'(?:search files for|search for literal) ' + _QUOTED):
        query = found.group(1)
        if not query.strip() or len(query) > 256:
            return abstain('search requires a bounded nonempty literal')
        action = {'name': 'search_files', 'arguments': {'query': query}}
    if action is None:
        return abstain('outside narrow single-action grammar; use normal fallback')
    return dict(status='proposal', action=action,
                reason='complete explicit single-action grammar matched; intent not independently verified',
                candidate_version=VERSION, executed=False, quality_validated=False)
