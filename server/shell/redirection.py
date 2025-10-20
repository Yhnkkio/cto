from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Redirection:
    path: str
    append: bool = False


@dataclass
class ParsedCommand:
    argv: List[str]
    redir: Optional[Redirection]


def parse_redirection(argv: List[str]) -> ParsedCommand:
    if not argv:
        return ParsedCommand([], None)
    # Look for > or >> in argv (simple implementation; ignores quoted variations)
    redir: Optional[Redirection] = None
    out: List[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == ">" or tok == ">>":
            if i + 1 >= len(argv):
                break
            path = argv[i + 1]
            redir = Redirection(path=path, append=(tok == ">>"))
            i += 2
        else:
            out.append(tok)
            i += 1
    return ParsedCommand(out, redir)
