# 🔍 DeveloperScope: Secure Code Review via Git + GPT-4

**DeveloperScope** is an automated secure-code review system designed for analyzing `merge commits` in Git repositories using GPT-4 function calling. It evaluates diffs, computes Halstead effort metrics, identifies high-severity issues, and generates human-readable HTML reports — all in one streamlined workflow.

---

## 🚀 Features

### 🧠 **AI-Powered Commit Analysis**
- Uses GPT-4.1 with JSON schema enforcement and function-calling.
- Classifies commit type: `Feature`, `Refactor`, `Bug‑fix`, etc.
- Detects potential issues with severity levels (`LOW` → `CRITICAL`).
- Suggests actionable fixes and refactorings.

### 🧾 **Halstead-Based Effort Estimation**
- Calculates *Halstead Effort* or *Volume* for all changed `.py` files.
- Provides an objective complexity metric per commit.

### 📂 **Smart File Context Retrieval**
- Model can fetch missing context via `get_file_contents()` if the `git diff` alone is not enough.
- Files are only retrieved on demand, minimizing noise and improving relevance.

### 🔁 **Two-Stage Secure Review**
- Feature commits go through a second pass for high/critical issues only.
- Ensures only the most relevant risks are surfaced to defenders.

### 📊 **Clean, Visual Reports**
- HTML reports generated per developer.
- Highlights commits with high effort or multiple issues.
- Sectioned by author, with summarized stats (average issues, effort breakdown, etc.).

### 📁 **Structured Output**
Produces a single JSON output:
```json
{
  "repo_name": "your_target_repo",
  "authors": {
    "username1": {
      "merge_requests": [ ... MergeRequestAnalysis objects ... ]
    },
    ...
  }
}
```

---

## 📁 Directory Overview

```
./
├── developerscope/
│   ├── __init__.py
│   ├── _types.py            # TypedDict definitions for structured output
│   ├── analyzer.py          # Git diff analysis + Halstead logic
│   ├── gpt.py               # Prompt templates + chat function orchestration
│   └── haslted.py           # Halstead effort calculations
├── iatskovskiivv.html       # Sample HTML report
├── main.py                  # Main analysis entry-point script
```

---

## 🛠️ Technologies Used

- **Python 3.12+**
- **GitPython** / **PyDriller**
- **Radon** – for Halstead metrics
- **OpenAI GPT-4.1 Function Calling**
- **Type-safe JSON Schema enforcement**
- **Semantic HTML + Embedded CSS** for reports

---

## 🧪 Example Report

<img src="https://i.imgur.com/yIW78gD.png" width="600" alt="Example HTML Report">

> ✅ Highlights:
> - Severity-based visual feedback
> - Halstead-driven complexity insight
> - Commit breakdown by type and effort

---

## ✅ Ideal For

- Engineering teams adopting **secure coding practices**
- Review automation in **CI pipelines**
- **Auditing** large or legacy Git histories
- Code quality insights in **refactoring cycles**
