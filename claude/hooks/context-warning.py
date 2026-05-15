#!/usr/bin/env python3
"""Warns when compaction fires, indicating context was near capacity."""
import sys

# Drain stdin (hook protocol requires it) without parsing
sys.stdin.read()

print("## Context Warning")
print()
print("Compaction completed — context was near or at capacity.")
print("Consider running `/compact` proactively around 50% usage,")
print("or `/handoff-create` if you need to continue in a fresh session.")
