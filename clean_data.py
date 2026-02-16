#!/usr/bin/env python3
"""Clean gate-code dataset for the Flex Gate & Locker Codes app.

Reads a JSON shaped like:
{
  "meta": {...},
  "groups": {
    "Community Name": [{"address": "...", "gate": "...", "type": "..."}],
    ...
  }
}

Writes:
- data.cleaned.json (merged community keys, normalized addresses/types, merged by address)

Usage:
  python clean_data.py data.json data.cleaned.json
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


DIGIT_RE = re.compile(r"\d+")
NON_ALNUM_TO_SPACE_RE = re.compile(r"[^a-z0-9]+")


def strip_accents(s: str) -> str:
  nfkd = unicodedata.normalize("NFKD", s or "")
  return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def clean_spaces(s: str) -> str:
  return " ".join((s or "").split()).strip()


def title_case_smart(s: str) -> str:
  small = {
    "a","an","and","as","at","but","by","for","from","in","into","near","nor","of",
    "on","or","over","the","to","up","via","with"
  }
  words = [w for w in clean_spaces(s).split(" ") if w]
  out: List[str] = []
  for i, w in enumerate(words):
    if w.isdigit():
      out.append(w)
      continue
    if len(w) <= 3 and w == w.upper() and any("A" <= c <= "Z" for c in w):
      out.append(w)
      continue
    lower = w.lower()
    if i != 0 and lower in small:
      out.append(lower)
    else:
      out.append(lower[:1].upper() + lower[1:])
  return " ".join(out)


def norm_community(name: str) -> str:
  base = strip_accents(clean_spaces(name)).lower()
  return clean_spaces(NON_ALNUM_TO_SPACE_RE.sub(" ", base))


def expand_abbrev_tokens(tokens: List[str]) -> List[str]:
  m = {
    "n":"north","s":"south","e":"east","w":"west",
    "ne":"northeast","nw":"northwest","se":"southeast","sw":"southwest",
    "rd":"road","st":"street","ave":"avenue","av":"avenue","blvd":"boulevard",
    "dr":"drive","ln":"lane","pl":"place","ct":"court","cir":"circle","trl":"trail",
    "pkwy":"parkway","hwy":"highway","mt":"mount","ste":"suite","apt":"apartment",
    "apts":"apartments","unit":"unit","bldg":"building",
  }
  return [m.get(t.lower(), t.lower()) for t in tokens]


def norm_address(addr: str) -> str:
  base = strip_accents(clean_spaces(addr)).lower()
  cleaned = clean_spaces(NON_ALNUM_TO_SPACE_RE.sub(" ", base))
  toks = [t for t in cleaned.split(" ") if t]
  return " ".join(expand_abbrev_tokens(toks))


def extract_gate_tokens(raw: str) -> List[str]:
  return DIGIT_RE.findall(raw or "")


def uniq_preserve(items: List[str]) -> List[str]:
  seen = set()
  out: List[str] = []
  for x in items:
    if x in seen:
      continue
    seen.add(x)
    out.append(x)
  return out


def most_common(values: List[str]) -> str:
  c = Counter([v for v in values if v])
  if not c:
    return ""
  return c.most_common(1)[0][0]


def norm_type(t: str) -> str:
  raw = clean_spaces(t).lower()
  k = clean_spaces(re.sub(r"[^a-z]+", " ", raw))
  if not k:
    return "Unknown"
  if k in {"apt","apts","apartment","apartments"} or "apartment" in k:
    return "Apartments"
  if k in {"residential","residence","home","homes","housing"} or "residential" in k:
    return "Residential"
  if k in {"business","businesses","commercial"} or "business" in k or "commercial" in k:
    return "Businesses"
  if "student" in k:
    return "Residential"
  return title_case_smart(k)


def clean_groups(groups: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
  buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
  for community, entries in (groups or {}).items():
    comm_norm = norm_community(str(community))
    if isinstance(entries, list):
      buckets[comm_norm].extend([e for e in entries if isinstance(e, dict)])

  out_groups: Dict[str, List[Dict[str, str]]] = {}
  for comm_norm, entries in buckets.items():
    display_comm = title_case_smart(comm_norm)

    by_addr: Dict[str, Dict[str, List[str]]] = {}
    for e in entries:
      address = clean_spaces(str(e.get("address","")))
      gate = clean_spaces(str(e.get("gate","")))
      typ = norm_type(str(e.get("type","")))

      addr_norm = norm_address(address)
      by_addr.setdefault(addr_norm, {"addresses":[], "types":[], "gates":[]})
      by_addr[addr_norm]["addresses"].append(address)
      by_addr[addr_norm]["types"].append(typ)
      by_addr[addr_norm]["gates"].append(gate)

    cleaned_entries: List[Dict[str, str]] = []
    for addr_norm, agg in by_addr.items():
      best_addr = most_common(agg["addresses"]) or title_case_smart(addr_norm)
      best_type = most_common(agg["types"]) or "Unknown"
      gate_tokens = uniq_preserve([t for g in agg["gates"] for t in extract_gate_tokens(g)])
      cleaned_entries.append({
        "address": best_addr,
        "gate": " ".join(gate_tokens),
        "type": best_type,
      })

    out_groups[display_comm] = cleaned_entries

  return out_groups


def main(argv: List[str]) -> int:
  if len(argv) != 3:
    print("Usage: python clean_data.py data.json data.cleaned.json", file=sys.stderr)
    return 2

  in_path, out_path = argv[1], argv[2]
  with open(in_path, "r", encoding="utf-8") as f:
    payload = json.load(f)

  groups = payload.get("groups", {})
  cleaned = clean_groups(groups)

  out_payload = {
    "meta": payload.get("meta", {}),
    "groups": cleaned,
  }
  with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out_payload, f, ensure_ascii=False, indent=2)

  print(f"Wrote {out_path} (communities={len(cleaned)})")
  return 0


if __name__ == "__main__":
  raise SystemExit(main(sys.argv))
