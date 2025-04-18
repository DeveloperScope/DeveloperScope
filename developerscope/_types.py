from typing import Literal, TypedDict

type MergeRequestEnum = Literal[
    "Feature",
    "Bug‑fix",
    "Refactor",
    "Performance",
    "Security‐patch",
    "Docs / comments",
    "Chore / dependency bump",
]

type IssueEnum = Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

type EffortEnum = Literal['Trivial', 'Minor', 'Moderate', 'Large', 'Major']

class PottentialIssue(TypedDict):
    filePath: str
    line: str
    issue: str
    proposedSolution: str
    level: IssueEnum
    

class MergeRequestAnalysis(TypedDict):
    hiddenReasoning: str
    type: MergeRequestEnum
    issues: list[PottentialIssue]
    effortEstimate: EffortEnum

class MergeRequestAnalysisResponse(MergeRequestAnalysis):
    author: str
    commitHash: str