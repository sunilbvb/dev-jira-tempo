"""CLI handler for `tempo-log ticket-map` command.

Manages persistent keyword-to-ticket mappings in .tempo-log/ticket-map.toml.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from ..ticket_mapper import TicketMapper

logger = logging.getLogger(__name__)


def run_ticket_map(args: argparse.Namespace, target: Any = None) -> int:
    """Execute ticket-map subcommands: list, add, match."""
    mapper = TicketMapper.load()
    action = getattr(args, "map_action", "list")

    if action == "list":
        if getattr(args, "json", False):
            print(json.dumps(mapper.mappings, indent=2))
        else:
            print("\nActive Keyword-to-Ticket Mappings (.tempo-log/ticket-map.toml):")
            print("=" * 55)
            if not mapper.mappings:
                print("  (no mappings defined yet)")
            for kw, ticket in sorted(mapper.mappings.items()):
                print(f"  {kw:<24} ->  {ticket}")
            print("=" * 55 + "\n")
        return 0

    if action == "add":
        kw = args.keyword.strip().lower()
        ticket = args.ticket.strip().upper()
        mapper.add_mapping(kw, ticket)
        saved_path = mapper.save()
        if getattr(args, "json", False):
            print(json.dumps({"keyword": kw, "ticket": ticket, "file": str(saved_path), "status": "saved"}))
        else:
            print(f"Added mapping: '{kw}' -> {ticket} (saved to {saved_path})")
        return 0

    if action == "match":
        query = args.query
        matched = mapper.match(query)
        if getattr(args, "json", False):
            print(json.dumps({"query": query, "matched_ticket": matched}))
        else:
            if matched:
                print(f"Match found: '{query}' -> {matched}")
            else:
                print(f"No ticket mapping matched for: '{query}'")
        return 0 if matched else 1

    return 0
