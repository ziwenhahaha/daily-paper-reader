#!/usr/bin/env python
# Boolean expression parsing and evaluation utilities:
# - Supports AND / OR / NOT, && / || / !, parentheses, and the author: prefix
# - Used by the BM25 path (Embedding does not run boolean logic)

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Optional


BOOLEAN_PATTERN = re.compile(r"\b(?:AND|OR|NOT)\b|&&|\|\||!", re.IGNORECASE)


@dataclass
class BoolNode:
  kind: str
  value: str = ""
  left: Optional["BoolNode"] = None
  right: Optional["BoolNode"] = None


def normalize_spaces(text: str) -> str:
  return re.sub(r"\s+", " ", str(text or "")).strip()


def has_boolean_syntax(text: str) -> bool:
  raw = str(text or "")
  if not raw:
    return False
  if "(" in raw or ")" in raw:
    return True
  return bool(BOOLEAN_PATTERN.search(raw))


def is_author_term(term: str) -> bool:
  t = normalize_spaces(term).lower()
  return t.startswith("author:")


def strip_outer_quotes(text: str) -> str:
  s = normalize_spaces(text)
  if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
    return s[1:-1].strip()
  return s


def clean_expr_for_embedding(expr: str) -> str:
  """
  Clean a boolean expression into a natural-language phrase usable by the vector path:
  - Remove logical operators and parentheses
  - For the author: prefix, keep only the author value
  """
  if not expr:
    return ""
  s = str(expr)
  s = s.replace("(", " ").replace(")", " ")
  s = re.sub(r"\bAND\b|\bOR\b|\bNOT\b|&&|\|\||!", " ", s, flags=re.IGNORECASE)
  s = re.sub(r"\bauthor\s*:\s*", " ", s, flags=re.IGNORECASE)
  s = normalize_spaces(s)
  return strip_outer_quotes(s)


def _tokenize(expr: str) -> List[str]:
  src = str(expr or "")
  out: List[str] = []
  i = 0
  n = len(src)

  while i < n:
    ch = src[i]
    if ch.isspace():
      i += 1
      continue
    if ch == "(":
      out.append("(")
      i += 1
      continue
    if ch == ")":
      out.append(")")
      i += 1
      continue
    if i + 1 < n and src[i : i + 2] == "&&":
      out.append("AND")
      i += 2
      continue
    if i + 1 < n and src[i : i + 2] == "||":
      out.append("OR")
      i += 2
      continue
    if ch == "!":
      out.append("NOT")
      i += 1
      continue

    # author:"xxx yyy" / author:'xxx yyy' is treated as a single term
    author_quoted = re.match(r"author\s*:\s*\"([^\"]+)\"", src[i:], flags=re.IGNORECASE)
    if author_quoted:
      out.append(f"author:{author_quoted.group(1)}")
      i += author_quoted.end()
      continue
    author_quoted_single = re.match(r"author\s*:\s*'([^']+)'", src[i:], flags=re.IGNORECASE)
    if author_quoted_single:
      out.append(f"author:{author_quoted_single.group(1)}")
      i += author_quoted_single.end()
      continue

    if ch in ('"', "'"):
      quote = ch
      i += 1
      start = i
      while i < n and src[i] != quote:
        i += 1
      out.append(src[start:i])
      if i < n and src[i] == quote:
        i += 1
      continue

    start = i
    while i < n and (not src[i].isspace()) and src[i] not in "()":
      i += 1
    token = src[start:i]
    upper = token.upper()
    if upper in ("AND", "OR", "NOT"):
      out.append(upper)
    else:
      out.append(token)

  # Insert an implicit AND (e.g. "A B" or ") A")
  fixed: List[str] = []
  prev_type = ""
  for tk in out:
    curr_type = "TERM"
    if tk in ("AND", "OR", "NOT", "(", ")"):
      if tk in ("AND", "OR", "NOT"):
        curr_type = "OP"
      elif tk == "(":
        curr_type = "LP"
      else:
        curr_type = "RP"

    if fixed:
      need_implicit_and = (
        prev_type in ("TERM", "RP")
        and curr_type in ("TERM", "LP", "OP")
        and tk != "OR"
        and tk != "AND"
      )
      if need_implicit_and:
        fixed.append("AND")

    fixed.append(tk)
    if curr_type == "TERM":
      prev_type = "TERM"
    elif curr_type == "LP":
      prev_type = "LP"
    elif curr_type == "RP":
      prev_type = "RP"
    else:
      prev_type = "OP"

  return fixed


class _Parser:
  def __init__(self, tokens: List[str]):
    self.tokens = tokens
    self.pos = 0

  def _peek(self) -> str:
    if self.pos >= len(self.tokens):
      return ""
    return self.tokens[self.pos]

  def _eat(self, token: str) -> bool:
    if self._peek() == token:
      self.pos += 1
      return True
    return False

  def parse(self) -> Optional[BoolNode]:
    if not self.tokens:
      return None
    node = self._parse_or()
    if node is None:
      return None
    if self.pos != len(self.tokens):
      return None
    return node

  def _parse_or(self) -> Optional[BoolNode]:
    node = self._parse_and()
    if node is None:
      return None
    while self._eat("OR"):
      right = self._parse_and()
      if right is None:
        return None
      node = BoolNode(kind="OR", left=node, right=right)
    return node

  def _parse_and(self) -> Optional[BoolNode]:
    node = self._parse_not()
    if node is None:
      return None
    while self._eat("AND"):
      right = self._parse_not()
      if right is None:
        return None
      node = BoolNode(kind="AND", left=node, right=right)
    return node

  def _parse_not(self) -> Optional[BoolNode]:
    if self._eat("NOT"):
      child = self._parse_not()
      if child is None:
        return None
      return BoolNode(kind="NOT", left=child)
    return self._parse_primary()

  def _parse_primary(self) -> Optional[BoolNode]:
    tk = self._peek()
    if not tk:
      return None
    if tk == "(":
      self.pos += 1
      node = self._parse_or()
      if node is None:
        return None
      if not self._eat(")"):
        return None
      return node
    if tk in ("AND", "OR", "NOT", ")"):
      return None
    self.pos += 1
    return BoolNode(kind="TERM", value=tk)


def parse_boolean_expr(expr: str) -> Optional[BoolNode]:
  raw = normalize_spaces(expr)
  if not raw:
    return None
  tokens = _tokenize(raw)
  parser = _Parser(tokens)
  return parser.parse()


def _normalize_doc_field(text: str) -> str:
  s = normalize_spaces(text).lower()
  return f" {s} " if s else " "


def match_term(term: str, title: str, abstract: str, authors: List[str]) -> bool:
  t = strip_outer_quotes(term).strip()
  if not t:
    return False

  text_scope = _normalize_doc_field(f"{title or ''}\n{abstract or ''}")
  authors_scope = _normalize_doc_field(" ; ".join(str(a or "") for a in (authors or [])))

  lower_t = t.lower()
  if lower_t.startswith("author:"):
    raw_author = strip_outer_quotes(t.split(":", 1)[1] if ":" in t else "")
    if not raw_author:
      return False
    key = _normalize_doc_field(raw_author.lower())
    return key in authors_scope

  key = _normalize_doc_field(lower_t)
  return key in text_scope


def evaluate_expr(node: Optional[BoolNode], title: str, abstract: str, authors: List[str]) -> bool:
  if node is None:
    return False
  if node.kind == "TERM":
    return match_term(node.value, title, abstract, authors)
  if node.kind == "NOT":
    return not evaluate_expr(node.left, title, abstract, authors)
  if node.kind == "AND":
    return evaluate_expr(node.left, title, abstract, authors) and evaluate_expr(
      node.right, title, abstract, authors
    )
  if node.kind == "OR":
    return evaluate_expr(node.left, title, abstract, authors) or evaluate_expr(
      node.right, title, abstract, authors
    )
  return False


def split_or_branches(node: Optional[BoolNode]) -> List[BoolNode]:
  if node is None:
    return []
  if node.kind == "OR":
    return split_or_branches(node.left) + split_or_branches(node.right)
  return [node]


def collect_positive_terms(node: Optional[BoolNode], negated: bool = False) -> List[str]:
  if node is None:
    return []
  if node.kind == "TERM":
    if negated:
      return []
    term = strip_outer_quotes(node.value)
    if not term:
      return []
    if is_author_term(term):
      return []
    return [term]
  if node.kind == "NOT":
    return collect_positive_terms(node.left, not negated)
  if node.kind in ("AND", "OR"):
    return collect_positive_terms(node.left, negated) + collect_positive_terms(node.right, negated)
  return []


def collect_unique_positive_terms(node: Optional[BoolNode]) -> List[str]:
  seen = set()
  out: List[str] = []
  for t in collect_positive_terms(node):
    key = normalize_spaces(t).lower()
    if not key or key in seen:
      continue
    seen.add(key)
    out.append(t)
  return out
