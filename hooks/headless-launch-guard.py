#!/usr/bin/env python3
"""PreToolUse guard: block raw Codex / Grok / headless-Claude launches.

Every headless worker must start through a headless wrapper
(~/.agents/skills/headless/scripts/run-{claude,codex,grok}.sh). The wrappers enforce
explicit model/effort/speed from their catalogs and the WarFleet roster check, so this
guard only has to stop launches that bypass them:

  codex <anything but a management subcommand>   e.g. codex exec, codex resume, codex "..."
  grok  <anything but a management subcommand>   e.g. grok -p, grok --single
  claude -p | --print                             (interactive/management claude is fine)

Only words in command position count. Quoted text, file paths such as ~/.claude/..., and
the bodies of heredocs that are not fed to a shell are data, not commands.
Exit 0 = allow; exit 2 = block (reason on stderr, plus a {"decision": "block"} line on stdout
for hosts such as Hermes that read stdout). `<engine> <subcommand> --help` is allowed.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

WRAPPERS = "~/.agents/skills/headless/scripts/run-{engine}.sh"
MANAGEMENT = {
    "codex": {"login", "logout", "debug", "mcp", "app-server", "features", "help", "completion",
              "--help", "-h", "--version", "-V", "version", "doctor"},
    "grok": {"models", "login", "logout", "sessions", "inspect", "doctor", "version", "v", "update",
             "mcp", "memory", "export", "trace", "worktree", "completions", "plugin", "setup", "leader",
             "help", "du", "usage", "--help", "-h", "--version", "-V"},
}
PREFIXES = {"env", "command", "exec", "nohup", "time", "sudo", "nice", "builtin"}
KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "{", "(", "time"}
SHELLS = {"sh", "bash", "zsh", "dash"}
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HELP = {"--help", "-h"}
REDIRECT = re.compile(r"^\d*(?:>>?|<|>&|&>)\S*$")  # 2>&1, >out.txt, 2>/dev/null


def strip_data_heredocs(command: str) -> str:
    """Drop heredoc bodies unless the heredoc feeds a shell interpreter."""
    lines = command.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        match = HEREDOC.search(line)
        if not match:
            i += 1
            continue
        delimiter = match.group(2)
        before = line[:match.start()]
        feeds_shell = bool(re.search(r"(?:^|[\s;|&(])(?:sh|bash|zsh|dash)(?:\s+-s)?\s*$", before)) or \
            bool(re.search(r"\|\s*(?:sh|bash|zsh|dash)\b", line[match.end():]))
        j = i + 1
        body = []
        while j < len(lines) and lines[j].strip() != delimiter:
            body.append(lines[j])
            j += 1
        if feeds_shell:
            out.extend(body)
        i = j + 1 if j < len(lines) else j
    return "\n".join(out)


def segments(command: str) -> list[str]:
    """Split on unquoted separators; $( and backticks start new segments even in double quotes."""
    parts, buf, quote, i = [], [], None, 0
    while i < len(command):
        c = command[i]
        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = None
        elif c == "\\" and i + 1 < len(command):
            buf.append(command[i:i + 2])
            i += 1
        elif command.startswith("$(", i) or c == "`":
            parts.append("".join(buf))
            buf = []
            i += 2 if c == "$" else 1
            continue
        elif quote == '"':
            buf.append(c)
            if c == '"':
                quote = None
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c in "\n;|&()":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def words(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def verdict(segment: str, depth: int = 0) -> str | None:
    toks = words(segment)
    while toks and (toks[0] in KEYWORDS or toks[0] in PREFIXES or ASSIGN.match(toks[0])):
        head = toks.pop(0)
        if head == "timeout" and toks:
            toks.pop(0)
    if not toks:
        return None
    exe = os.path.basename(toks[0])
    args = toks[1:]
    if exe == "timeout" and args:
        return verdict(" ".join(shlex.quote(a) for a in args[1:]), depth)
    if exe in SHELLS and len(args) >= 2 and args[0] == "-c" and depth < 3:
        for inner in segments(strip_data_heredocs(args[1])):
            reason = verdict(inner, depth + 1)
            if reason:
                return reason
        return None
    flags = [a for a in args[1:] if not REDIRECT.match(a)]
    if exe in ("codex", "grok", "claude") and len(args) >= 2 and flags and all(a in HELP for a in flags):
        return None  # `<engine> <subcommand> --help` prints usage and starts no model
    if exe in ("codex", "grok"):
        if args and args[0] in MANAGEMENT[exe]:
            return None
        if not args:
            return f"raw {exe} session"
        return f"raw {exe} launch ({exe} {args[0]})"
    if exe == "claude" and any(a in ("-p", "--print") or a.startswith("--print=") for a in args):
        return "raw headless claude launch (claude -p)"
    if exe == "codex-companion.mjs" or (exe in ("node", "nodejs") and args
                                        and os.path.basename(args[0]) == "codex-companion.mjs"):
        return "codex companion launch"
    return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        sys.exit(0)
    # Codex supplies patch text in tool_input.command too. Only the dedicated
    # file-editing tool is exempt; shell commands containing patches still pass
    # through the launch parser, including executable command substitutions.
    if data.get("tool_name") in {"apply_patch", "functions.apply_patch"}:
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str) or not command.strip():
        sys.exit(0)
    for segment in segments(strip_data_heredocs(command)):
        reason = verdict(segment)
        if reason:
            engine = "claude" if "claude" in reason else "grok" if "grok" in reason else "codex"
            sys.stderr.write(
                f"BLOCKED by headless launch guard: {reason}.\n"
                f"Launch workers only through {WRAPPERS.format(engine=engine)} with explicit "
                "--model/--effort (and --speed for Claude/Codex); WarFleet units also pass "
                "--auth/--task-id. Management and read-only commands are allowed. Ask the user "
                "if this block looks wrong; never reshape a command to slip past it.\n")
            # Hosts that read a stdout decision instead of exit 2 (Hermes) block on this line.
            print(json.dumps({"decision": "block", "reason": f"headless launch guard: {reason}"}))
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
