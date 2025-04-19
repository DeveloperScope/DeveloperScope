from typing import Literal, NotRequired, TypedDict

###########################################
### Merge Request And Repo Analysis Types

type MergeRequestEnum = Literal[
    "Feature",
    "Bug‑fix",
    "Refactor",
    "Performance",
    "Security‐patch",
    "Docs / comments",
    "Chore / dependency bump",
]

type IssueEnum = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

type EffortEnum = Literal["Trivial", "Minor", "Moderate", "Large", "Major"]


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


class CommitMetrics(TypedDict):
    halstedEffort: float
    cyclomaticComplexity: NotRequired[int]


class DetailedMergeRequestAnalysis(MergeRequestAnalysis):
    commitHash: str
    metrics: CommitMetrics


class Branch(TypedDict):
    branch: str
    mergeRequests: list[DetailedMergeRequestAnalysis]


class AuthorsAnalysis(TypedDict):
    author: str
    summary: str
    branches: list[Branch]


###########################################
### Stat


class CommitStatus(TypedDict):
    commitHash: str
    status: Literal[
        "NEW"
        "PENDING",
        "DONE",
    ]


class BranchStats(TypedDict):
    name: str
    commits: list[CommitStatus]


class AuthorStats(TypedDict):
    name: str
    email: str
    branches: list[BranchStats]


class RepositoryStats(TypedDict):
    url: str
    authors: list[AuthorStats]
    status: Literal["NEW", "CLONED", "PENDING", "DONE"]
