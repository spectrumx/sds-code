#!/usr/bin/env python3
"""Merge rendered federation.toml with existing peers (preserve add-peer entries by fqdn)."""

import re
import sys
from pathlib import Path


def split_site_and_peers(text: str):
    parts = re.split(r"\n\[\[peers\]\]\n", text, maxsplit=0)
    site = parts[0].rstrip() + "\n"
    peers = [p.strip() for p in parts[1:] if p.strip()]
    return site, peers


def peer_fqdn(block: str):
    match = re.search(r'^fqdn\s*=\s*"([^"]*)"', block, re.MULTILINE)
    return match.group(1) if match else None


def peer_ca_cert_path(block: str):
    match = re.search(r'^ca_cert_path\s*=\s*"([^"]*)"', block, re.MULTILINE)
    return match.group(1) if match else None


def merge_ca_from_existing(rendered_block: str, existing_block: str) -> str:
    if peer_ca_cert_path(rendered_block):
        return rendered_block
    ca = peer_ca_cert_path(existing_block)
    if not ca:
        return rendered_block
    return rendered_block.rstrip() + f'\nca_cert_path = "{ca}"\n'


def main() -> None:
    rendered_path, existing_path, out_path = sys.argv[1:4]
    rendered_site, rendered_peers = split_site_and_peers(
        Path(rendered_path).read_text()
    )
    _, existing_peers = split_site_and_peers(Path(existing_path).read_text())
    existing_by_fqdn = {fqdn: p for p in existing_peers if (fqdn := peer_fqdn(p))}
    rendered_fqdns = {fqdn for p in rendered_peers if (fqdn := peer_fqdn(p))}
    extra_peers = [
        p
        for p in existing_peers
        if (fqdn := peer_fqdn(p)) and fqdn not in rendered_fqdns
    ]

    merged_rendered = []
    for peer_block in rendered_peers:
        fqdn = peer_fqdn(peer_block)
        merged = peer_block
        if fqdn and fqdn in existing_by_fqdn:
            merged = merge_ca_from_existing(peer_block, existing_by_fqdn[fqdn])
        merged_rendered.append(merged)

    lines = [rendered_site.rstrip(), ""]
    for block in merged_rendered + extra_peers:
        lines.append("[[peers]]")
        lines.append(block)
        lines.append("")
    Path(out_path).write_text("\n".join(lines).rstrip() + "\n")


if __name__ == "__main__":
    main()
