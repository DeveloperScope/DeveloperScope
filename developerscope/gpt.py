SYSTEM_PROMPT = """
You are a secure‑code reviewer.

You will receive:
• The raw `git diff` of a **merge commit**
• The *Halstead total volume* for the changed Python files (objective metric)

Your tasks:
1. **Classify** the merge request type – choose exactly one from the predefined list.
2. **Identify potential issues** (security, logic, maintainability, best practices, etc.), each with a severity level: LOW, MEDIUM, HIGH, or CRITICAL.
3. If the `git diff` is insufficient for full understanding, call **get_file_contents** with the exact file paths you need.
4. Return the result strictly as JSON matching the `MergeRequestAnalysis` format.
5. For each identified issue, propose a specific and technically actionable improvement by:**
   • Rewriting affected lines with corrected or optimized code that resolves the issue  
   • Describing precise refactoring steps (e.g., "Extract the database logic into a separate `Repository` class", "Add `isinstance()` check before casting", "Use constant-time comparison for sensitive data", etc.)

If more context is needed, return nothing and instead call `get_file_contents`. Do not make assumptions without proper file context. You may call `get_file_contents` as many times as needed, but aim to retrieve all relevant files in a single call when possible.
"""

SYSTEM_PROMPT_REVIEW = """
You are a senior secure‑code *defender* reviewing an *existing* analysis.

1. You MUST retrieve all relevant files associated with reported issues by calling `get_file_contents` – even if the initial report seems valid.
2. Then, **copy the existing analysis**, but:
   • **Keep only** issues with severity HIGH or CRITICAL.
   • Reevaluate and **remove or adjust** any overstated concerns.
   • Optionally suggest a better fix or explain why a previously reported issue is invalid or non‑critical.

Output the result strictly as a `MergeRequestAnalysis` JSON object.
"""


SYSTEM_PROMPT_REPORT_GENERATOR = """
You are a helpful assistant that generates clean, minimal, and readable HTML reports for software engineering analysis.

You receive a raw Python-style data string representing commit analyses for one or more developers. Each entry includes:
- commit hash (short)
- effort estimate (e.g., "Trivial", "Minor", "Moderate", "Large", "Major")
- issue count (integer)
- author name or ID

Your task is to convert this into a clean and compact HTML page with:
- a table listing the analyzed commits
- one section per developer (if multiple)
- short summary statistics (e.g., average issues, most common effort)
- simple CSS styling for readability (use embedded `<style>`)
- highlight commits with 3+ issues or "Major" effort visually (bold or colored row)

Use semantic HTML (`<section>`, `<table>`, `<thead>`, `<tbody>`, etc.). Keep it visually appealing but minimal — no JavaScript, no external fonts.

Assume the user will paste the full raw data in the user message. Do not explain the result — just return the HTML content.
"""


from pathlib import Path
import git

from developerscope.analyzer import get_current_state_paths


def tool_get_file_contents(
    targer_commit: git.Commit | None = None, files: list[str] = ["example.txt"]
):
    if targer_commit is not None:
        files = get_current_state_paths(targer_commit)
    return {
        "type": "function",
        "name": "get_file_contents",
        "description": "Function which accepts a list of files in a git repo and produces a their content",
        "strict": True,
        "parameters": {
            "type": "object",
            "required": ["files"],
            "properties": {
                "files": {
                    "type": "array",
                    "description": "List of specific files to read from the git repository",
                    "items": {
                        "type": "string",
                        "enum": files,
                        "description": "File name that exists in the git repository",
                    },
                }
            },
            "additionalProperties": False,
        },
    }


from developerscope.analyzer import get_prompt_for_merge_commit


def get_input_messages_analyzer(targer_commit: git.Commit):
    input_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": get_prompt_for_merge_commit(targer_commit)},
    ]

    return input_messages

def get_review_input_messages(response):
    input_messages = [
    {
      "role": "system",
      "content": SYSTEM_PROMPT_REVIEW
    },
    {
      "role": "user",
      "content": response.text
    }
    ]
    return input_messages


from developerscope._types import MergeRequestAnalysis
import json
from openai import AsyncOpenAI

client = AsyncOpenAI()

with open("schema.json") as file:
    schemaMergeRequest = json.load(file)


async def _get_response(input_messages, tools, required_tool: bool | None):
    if required_tool:
        tool_choice = "required"
    elif required_tool is None:
        tool_choice = "none"
    else:
        tool_choice = "auto"
    return await client.responses.create(
        model="gpt-4.1",
        input=input_messages,
        text={"format": schemaMergeRequest},
        temperature=0.2,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=False,
    )


from developerscope.analyzer import get_current_state


def call_function(name, args, commit: git.Commit):
    if name == "get_file_contents":
        return get_current_state(commit, args["files"])


from developerscope._types import MergeRequestAnalysis
import json
from openai import AsyncOpenAI


async def run_chat_with_functions(input_messages, tools, target_commit: git.Commit, required_tool=True):
    max_calls = 3
    for i in range(max_calls):
        if i == max_calls - 1:
            required_tool = None  # means forbidden
        response = await _get_response(
            input_messages, tools, required_tool=required_tool if tools else False
        )

        if response.output[0].type == "message":
            return response.output[0].content[0]
        if response.output[0].type == "function_call":
            tool_call = response.output[0]
            input_messages.append(dict(tool_call))
            name = tool_call.name
            args = json.loads(tool_call.arguments)
            print(name, args)
            result = call_function(name, args, target_commit)
            input_messages.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": str(result),
                }
            )
            required_tool = False

    return response.output[0].content[0]


async def anylyze_commit(target_commit: git.Commit):
    tools = [tool_get_file_contents(target_commit), ]
    input_messages = get_input_messages_analyzer(target_commit)
    response = await run_chat_with_functions(input_messages, tools, target_commit)
    input_messages = get_review_input_messages(response)
    response = await run_chat_with_functions(input_messages, tools, target_commit)
    return response.text


async def generate_html_report_for_author(
    author: str,
    data: str,
    client
):
    input_messages = [
        {"role": "system", "content": SYSTEM_PROMPT_REPORT_GENERATOR},
        {"role": "user", "content": data},
    ]

    response = await client.responses.create(
        model="gpt-4.1",
        input=input_messages,
    )

    html_output = response.content.strip()

    output_path = Path(f"{author}.html")
    output_path.write_text(html_output, encoding="utf-8")

    print(f"✅ Report saved to: {output_path}")
