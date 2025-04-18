SYSTEM_PROMPT = """
You are a secure‑code reviewer.

You will receive:
• the raw `git diff` of a **merge commit**
• the *Halstead total volume* for the changed Python files (objective metric)

Tasks:
1. **Classify** the merge‑request type – choose exactly one from the list.
2. **List potential issues** (security, logic, best practice, etc.) with a severity of LOW‑CRITICAL.
3. If the diff alone is insufficient, call **get_file_contents** with the exact file‑paths you still need.
Return the result strictly as JSON conforming to the MergeRequestAnalysis

OR return nothing and call the `get_file_contents` function. Answer with json only if you think its right thing to do.
Don't shy and request files as much as you want. Try to make only one call, include all interesting files. But it is up to you to make sequential calls"""

SYSTEM_PROMPT_REVIEW = """
You are a senior secure‑code *defender* reviewing an *existing* analysis.

1. **If** you need more context, call `get_file_contents`.
2. **Then** copy the existing analysis but *keep only* issues with severity HIGH
   or CRITICAL.
3. Adjust `effortEstimate` if the filtered list changes the scope.
Output the same `MergeRequestAnalysis` object.
"""


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