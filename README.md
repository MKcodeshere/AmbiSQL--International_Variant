# AmbiSQL — OpenAI (International) Variant

This repository is a practical replication of the original AmbiSQL project with changes that make it work reliably outside Mainland China. In particular, the original text2SQL model `XGenerationLab/XiYanSQL-QwenCoder-32B-2504` hosted on ModelScope is not accessible in many regions. This variant replaces that dependency with OpenAI’s GPT‑4.1 and ships a Streamlit frontend for quick testing — while keeping the core AmbiSQL workflow and giving full credit to the authors’ work.

- Original project (credits): https://github.com/JustinzjDing/AmbiSQL/tree/main
- This project: AmbiSQL with OpenAI GPT‑4.1 + Streamlit, plus a few robustness fixes

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

## Why this variant

- ModelScope access: `XGenerationLab/XiYanSQL-QwenCoder-32B-2504` can be blocked or rate‑limited outside CN. We switched the SQL generation calls to use OpenAI GPT‑4.1 via the official OpenAI client so it runs globally.
- Frontend options: Added a root‑level Streamlit app (`streamlit_app.py`) for quick local testing, in addition to the provided React/Vite `chatbox/` app.
- Reliability: Fixed a number of cross‑platform and UX issues (Windows paths, CSV encodings, SQL code‑fence sanitation, clear 401 handling, etc.).

## What’s different from upstream

- LLM providers
  - Ambiguity detection and preference tree calls use a configurable OpenAI‑compatible endpoint (DashScope or OpenAI) via `server/llm_call.py`.
  - SQL generation (previously ModelScope) now uses OpenAI GPT‑4.1 by default. You may set a different model via `SQL_MODEL_ID`.

- Backend stability
  - Added `server/config.py` to standardize a workspace directory and auto‑create it at startup.
  - Improved CSV reading in `server/schema_generator.py` with encoding fallbacks (`utf‑8`, `utf‑8‑sig`, `cp1252`, `latin1`).
  - Sanitizes model output SQL to strip markdown code fences (```/```sql) before executing.
  - Added a `/api/sql/compare` endpoint that executes the raw and clarified SQL and returns structured results.
  - Clarified the behavior for `additional_info`: it refines the question but does not trigger a new ambiguity round.

- Frontend (Streamlit)
  - Root `streamlit_app.py` mirrors the React chat flow:
    - Analyze → render ambiguity choices → submit clarifications (+ optional additional info) → generate SQL.
    - Compare button calls the new `/api/sql/compare` and renders row counts + dataframes.

## ✨ Key Features

*   **Automatic Ambiguity Detection:** Identifies and classifies ambiguous phrases in the user's query based on a systematic ambiguity taxonomy.
*   **Interactive Clarification:** Generates intuitive multiple-choice questions to let the user clarify their exact intent.
*   **Query Rewriting:** Incorporates user feedback to construct a new, unambiguous natural language query.
*   **Improved SQL Accuracy:** Provides a clean, precise query to a downstream Text-to-SQL system, boosting the accuracy of the generated SQL.




## 🚀 Getting Started (this variant)



### 1) Backend

```
cd server
create virtual environment using uv or python, then activate 
pip install -r requirements.txt

```

Set api_key variables with your own api_key in llm.py and server.py under server folder
```

Run the backend:

```
python server/server.py
```

### 3) Frontend



```
streamlit run streamlit_app.py
```


## ⚙️ How It Works: An Example


<p align="center">
  <img src="figs/demo_ui.png" alt="AmbiSQL Demonstration">
</p>


The user interface is split into three main panels: User Input, Ambiguity Resolution, and SQL Generation.

1.  **User Input Panel `①`:**
    A user enters an ambiguous query, such as *"How many drivers born after the Vietnam War have been ranked 2?"*. They can also select the database and SQL dialect. For quick exploration, users can also load predefined examples from our dataset.

2.  **Ambiguity Resolution Panel `②`:**
    AmbiSQL detects ambiguities and presents clarification questions:
    *   For **"the end of the Vietnam War,"** it asks the user to choose a specific date (e.g., end date, or just the year).
    *   For **"ranked 2,"** it presents a choice of relevant database columns (e.g., `rank`, `position`, `positionOrder`), showing a data snippet for context.
    The user selects their desired options from dropdown menus. They can also add optional constraints, like specifying the driver's nationality.

3.  **SQL Generation Panel `③`:**
    After clarification, AmbiSQL rewrites the query and sends it to the downstream Text-to-SQL model ([XiYan-SQL](https://xgenerationlab-xiyan-qwen-instruct.ms.show/?) in our example). This panel displays a side-by-side comparison:
    *   **Without AmbiSQL:** The SQL generated from the original, ambiguous query is often incorrect.
    *   **With AmbiSQL:** The SQL generated from the clarified query accurately reflects the user's intent.

The **`Compare`** button executes both SQLs against the local SQLite database and returns row counts and rows for inspection.

## 📚 Credits & License

- Original AmbiSQL project (credits): https://github.com/JustinzjDing/AmbiSQL/tree/main
- This repository adapts the backend to OpenAI GPT‑4.1, adds a Streamlit frontend, and improves cross‑platform reliability.

This project is licensed under the [Apache License 2.0](LICENSE).
