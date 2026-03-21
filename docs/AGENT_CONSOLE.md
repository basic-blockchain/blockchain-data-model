# Agent Team Console (Interactive)

## What it is
A console-first interactive orchestrator that simulates a high-level development team:
- TL
- Architect
- SeniorDev
- QA
- DevSecOps

It shows:
- tasks assigned between roles
- role replies
- terminal commands entered
- terminal stdout/stderr output
- command exit codes

## Run

```bash
py scripts/dev_team_console.py
```

## Core commands

```text
help
stream on|off
logs [n]
wait [segundos]
roles
status
ask <rol> <mensaje>
kickoff <objetivo>
run <comando-shell>
exit
```

## Example session

```text
kickoff Construir interfaz interactiva de auditoria DevSecOps
ask tl Define plan de entrega en 3 fases
wait 2
run git status --short
logs 30
```

## Notes
- This first version is console-based and local.
- Team behavior is deterministic and role-based.
- Next iteration can add a graphical UI (web dashboard or TUI with panes).
