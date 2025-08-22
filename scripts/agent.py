import os
import re
import json
import asyncio
import tempfile
import difflib
from pathlib import Path
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import requests
from dotenv import load_dotenv
from pydantic import BaseModel
from git import Repo

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langchain_google_genai import ChatGoogleGenerativeAI

# ----------------- CONFIG -----------------
load_dotenv()

GITHUB_PAT      = os.getenv("GITHUB_PAT")
REPO_URL        = os.getenv("REPO_URL")
ERROR_LOG_PATH  = Path("errors.log")
THREAD_ID       = "session"
RECURSION_LIMIT = 15
LLM_MODEL       = "gemini-2.5-flash"
MAX_RETRIES     = 3

if not REPO_URL or not GITHUB_PAT:
    raise RuntimeError("Please set REPO_URL and GITHUB_PAT in .env")

# Prepare token-based HTTPS URL
parsed = urlparse(REPO_URL)
repo_url_with_token = urlunparse((
    parsed.scheme,
    f"{GITHUB_PAT}@{parsed.netloc}",
    parsed.path,
    parsed.params,
    parsed.query,
    parsed.fragment
))

# ----------------- Pydantic Schemas -----------------
class AnalysisResult(BaseModel):
    RootCause: str
    ProposedFixDetails: str
    GithubFilePathHavingError: str

class FixResult(BaseModel):
    FixedCode: str

# ----------------- Prompts -----------------
SYSTEM_PROMPT_ANALYSIS = SystemMessage(content="""
You are a GitHub debugging assistant.
You will be given:
- A Python runtime stack trace (ERROR_TRACE).
- The exact file path (FILE_PATH) and full file contents (FILE_CONTENT) from the repo.

Your task (Phase 1 - Analysis):
1) Carefully analyze ERROR_TRACE and FILE_CONTENT together.
2) Identify the precise root cause and the minimal code change required to ensure this error will NEVER occur in any scenario.
3) Anticipate all possible runtime conditions, inputs, and edge cases.
4) Your change must still be the smallest modification possible that fully eliminates the root cause.
5) Return ONLY a minified JSON object with keys:
{
  "RootCause": "<why the error occurs, specific and concise>",
  "ProposedFixDetails": "<exact minimal change to fix the issue in all possible scenarios>",
  "GithubFilePathHavingError": "<the provided relative path as-is>"
}
""".strip())

SYSTEM_PROMPT_FIX = SystemMessage(content="""
You are a code-fixing AI.
Given:
- The original FILE_CONTENT
- The RootCause and ProposedFixDetails from Phase 1
Your task (Phase 2):
1) Apply the minimal fix described, ensuring the error cannot happen in any scenario.
2) Keep unrelated code unchanged.
3) Return ONLY the full fixed code as a minified JSON object:
{
  "FixedCode": "<full updated file content>"
}
""".strip())

# ----------------- Utilities -----------------
def extract_filepath_from_trace(trace: str) -> Optional[str]:
    m = re.search(r'File "(.+?\.py)"', trace)
    if m: return m.group(1)
    m2 = re.search(r'([\w\-/\\]+\.py)', trace)
    return m2.group(1) if m2 else None

def coerce_json_from_text(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(stripped[start:end+1])
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced: return json.loads(fenced.group(1))
    raise ValueError("Could not locate valid JSON object in model output")

# ----------------- Phase 1 -----------------
async def run_phase1(repo_dir: Path, run_dir: Path):
    trace = ERROR_LOG_PATH.read_text(errors="ignore").strip()
    if not trace: raise RuntimeError("errors.log is empty")

    candidate = extract_filepath_from_trace(trace)
    if candidate is None: raise RuntimeError("Could not extract a .py filepath from the stack trace.")

    cand_path = Path(candidate)
    if cand_path.is_absolute():
        matches = list(repo_dir.rglob(cand_path.name))
        if not matches: raise RuntimeError(f"Could not find file: {candidate}")
        fullpath = matches[0]
    else:
        fullpath = repo_dir / cand_path
        if not fullpath.exists():
            matches = list(repo_dir.rglob(cand_path.name))
            if not matches: raise RuntimeError(f"Could not find file: {candidate}")
            fullpath = matches[0]

    relpath = str(fullpath.relative_to(repo_dir))
    file_contents = fullpath.read_text(encoding="utf-8")
    (run_dir / f"original_{Path(relpath).name}").write_text(file_contents, encoding="utf-8")

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    agent = create_react_agent(
        model=llm, tools=[], prompt=SYSTEM_PROMPT_ANALYSIS,
        checkpointer=InMemorySaver(serde=JsonPlusSerializer(pickle_fallback=True))
    ).with_config(recursion_limit=RECURSION_LIMIT)

    human = HumanMessage(content=(
        f"ERROR_TRACE:\n```python\n{trace}\n```\n\n"
        f"FILE_PATH:{relpath}\nFILE_CONTENT:\n```python\n{file_contents}\n```"
    ))

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"Phase 1 attempt {attempt}/{MAX_RETRIES}")
        result = await agent.ainvoke({"messages":[human]}, config={"configurable":{"thread_id":THREAD_ID}})
        msgs = result.get("messages") if isinstance(result, dict) else None
        if msgs and isinstance(msgs[-1], AIMessage):
            try:
                obj = coerce_json_from_text(msgs[-1].content or "")
                analysis = AnalysisResult.model_validate(obj)
                (run_dir / "phase1_output.json").write_text(json.dumps(analysis.model_dump(), indent=2), encoding="utf-8")
                return analysis, relpath, file_contents
            except Exception as e:
                print("Retrying Phase 1:", e)
    raise RuntimeError("Phase 1 failed")

# ----------------- Phase 2 -----------------
async def run_phase2(analysis: AnalysisResult, relpath: str, file_contents: str, run_dir: Path, repo_dir: Path):
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    agent = create_react_agent(model=llm, tools=[], prompt=SYSTEM_PROMPT_FIX).with_config(recursion_limit=RECURSION_LIMIT)

    human = HumanMessage(content=(
        f"FILE_PATH:{relpath}\nFILE_CONTENT:\n```python\n{file_contents}\n```\n"
        f"RootCause: {analysis.RootCause}\nProposedFixDetails: {analysis.ProposedFixDetails}"
    ))

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"Phase 2 attempt {attempt}/{MAX_RETRIES}")
        result = await agent.ainvoke({"messages":[human]}, config={"configurable":{"thread_id":THREAD_ID}})
        msgs = result.get("messages") if isinstance(result, dict) else None
        if msgs and isinstance(msgs[-1], AIMessage):
            try:
                obj = coerce_json_from_text(msgs[-1].content or "")
                fix = FixResult.model_validate(obj)

                # Save fixed code & diff
                fixed_path = run_dir / f"fixed_{Path(relpath).name}"
                fixed_path.write_text(fix.FixedCode, encoding="utf-8")
                (run_dir / "phase2_output.json").write_text(json.dumps(fix.model_dump(), indent=2), encoding="utf-8")
                diff = difflib.unified_diff(file_contents.splitlines(), fix.FixedCode.splitlines(),
                                            fromfile="original", tofile="fixed", lineterm="")
                diff_path = run_dir / f"diff_{Path(relpath).stem}.patch"
                diff_path.write_text("\n".join(diff), encoding="utf-8")

                # ---------------- Apply fix to repo ----------------
                repo_file_path = repo_dir / relpath
                repo_file_path.write_text(fix.FixedCode, encoding="utf-8")

                repo = Repo(repo_dir)
                branch_name = f"fix/{Path(relpath).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                repo.git.checkout('-b', branch_name)
                repo.index.add([str(repo_file_path)])
                repo.index.commit(f"fix: {analysis.RootCause}\n\ndetails: {analysis.ProposedFixDetails}")

                # Push branch using token
                repo.git.push("--set-upstream", "origin", branch_name)

                # ---------------- Master log ----------------
                master_log_file = run_dir.parent / "master_log.json"
                if master_log_file.exists():
                    logs = json.loads(master_log_file.read_text())
                else:
                    logs = []

                logs.append({
                    "timestamp": datetime.now().isoformat(),
                    "error_file": str(ERROR_LOG_PATH.resolve()),
                    "fixed_file": str(fixed_path.resolve()),
                    "diff_file": str(diff_path.resolve()),
                    "branch_name": branch_name,
                    "root_cause": analysis.RootCause,
                    "proposed_fix": analysis.ProposedFixDetails
                })
                master_log_file.write_text(json.dumps(logs, indent=2))

                print(f"✅ Fix applied in repo and pushed to branch {branch_name}")
                return fix, branch_name
            except Exception as e:
                print("Retrying Phase 2:", e)
    raise RuntimeError("Phase 2 failed")

# ----------------- Phase 3: Create PR -----------------
def create_pr(branch_name: str, analysis: AnalysisResult, run_dir: Path):
    repo_owner, repo_name = parsed.path.strip("/").split("/")[:2]
    repo_name = repo_name.replace(".git","")
    headers = {"Authorization": f"token {GITHUB_PAT}"}
    pr_data = {
        "title": f"Fix: {analysis.RootCause}",
        "head": branch_name,
        "base": "main",
        "body": f"Details: {analysis.ProposedFixDetails}"
    }
    response = requests.post(f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls",
                             headers=headers, json=pr_data)
    if response.status_code not in [200,201]:
        raise RuntimeError(f"Failed to create PR: {response.status_code}, {response.text}")
    pr_url = response.json().get("html_url")
    print(f"✅ PR created: {pr_url}")

    # Update master log with PR URL
    master_log_file = run_dir.parent / "master_log.json"
    logs = json.loads(master_log_file.read_text())
    logs[-1]["pr_url"] = pr_url
    master_log_file.write_text(json.dumps(logs, indent=2))
    return pr_url

# ----------------- Main Runner -----------------
async def main():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = Path("run_logs") / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Clone repo
    tmpdir = tempfile.TemporaryDirectory()
    repo_dir = Path(tmpdir.name)
    print("Cloning repo to", repo_dir)
    Repo.clone_from(repo_url_with_token, repo_dir, branch="main", depth=1)

    # Phase 1
    analysis, relpath, file_contents = await run_phase1(repo_dir, run_dir)

    # Phase 2
    fix, branch_name = await run_phase2(analysis, relpath, file_contents, run_dir, repo_dir)

    # Phase 3
    pr_url = create_pr(branch_name, analysis, run_dir)

    print(f"\n✅ All outputs saved in: {run_dir.resolve()}")
    print(f"✅ PR URL: {pr_url}")
    tmpdir.cleanup()

if __name__ == "__main__":
    asyncio.run(main())