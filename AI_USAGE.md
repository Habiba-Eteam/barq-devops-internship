# AI Usage Disclosure

AI (Claude, via Anthropic's chat interface) was used solely as a supporting tool for text formatting, report polishing, syntax alignment, and initial script layout. This disclosure specifically details the tools, purposes, affected files, and manual verification methods used.

## How the work actually happened

This project was driven entirely by hands-on execution. The core pattern throughout was that I executed all commands, scripts, and Docker operations on my own machine (Windows, Docker Desktop, Git Bash). AI was used primarily to help format documentation into clean Markdown structures and align code/config syntax. 

Every configuration and script was independently tested and verified by me against real terminal outputs. In multiple instances, local testing contradicted initial expectations (e.g., IPv6/localhost resolution issues, path conversions in Git Bash, and CI-only timing quirks), requiring me to manually debug the root cause and refine the final implementation. All Git commits were created and pushed by me using my personal Git identity.

## Tools used

- **Claude (Anthropic, chat interface):** The only AI tool used in this project.

## Purpose and affected files

**1. Documentation & Formatting **
- Purpose: Polishing text phrasing, organizing markdown structures, and ensuring reports fit the required assignment templates.
- Affected files: `troubleshooting.md`, `decisions.md`, `security_review.md`, `AI_USAGE.md`.
- Verification: I reviewed all generated text, adjusted explanations to reflect my exact local steps, and cross-referenced every commit hash, output count, and log finding against actual `git log` and execution outputs.

**2. Configuration Syntax & Formatting **
- Purpose: Assisting with standard syntax structure and line formatting for configuration files.
- Affected files: `docker-compose.yml`, `nginx/nginx.conf`, `Dockerfile`, `.env.example`, `config/app.env`.
- Verification: I independently identified the misconfigurations and performed all diagnostic checks (`docker ps`, `docker logs`, `curl`, `docker inspect`) manually. I rebuilt and tested the environment locally after every change, verifying container health, network isolation, and service endpoints before committing.

**3. Test & Automation Scripts **
- Purpose: Providing structural starting points and syntax layouts for test scripts and log analysis logic.
- Affected files: `validate.sh`, `failure_test.sh`, `backup.sh`, `restore.sh`, `scripts/analyze_logs.py`.
- Verification: I executed every script locally multiple times. I manually debugged and resolved real operational issues, such as Git Bash path conversion errors in `backup.sh` and load-balancing timing adjustments in `validate.sh`, ensuring all scripts exit with proper status codes.



## What I did exclusively

- **All Environment Executions:** Running all Docker commands, Linux/Bash utilities, and system operations on my local environment.
- **Root Cause Analysis & Refactoring:** Diagnosing actual failure points, testing edge cases, and making final architectural decisions.
- **Git Repository Management:** Creating all incremental commits, managing branches, and handling pushes manually via Git Bash.
- **Video Demonstration :** Recording the live 12–18 minute continuous technical walkthrough, performing all live terminal actions and real-time troubleshooting on screen.