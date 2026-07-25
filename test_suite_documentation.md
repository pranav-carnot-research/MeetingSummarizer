# Documentation: Performance & Semantic Test Suite

This document describes the design, scenarios, execution instructions, and metrics for the Meeting Summarizer **Performance & Semantic Test Suite** (`performance_test_suite.py`).

---

## 1. Overview & Objective

The **Performance & Semantic Test Suite** is designed to benchmark the active LLM (currently configured to **Mistral** via Ollama) and post-processing filters on real meeting transcripts. Unlike unit tests (which use mocks to run in milliseconds), this suite executes the actual AI pipeline locally to measure:

1. **Inference Latency:** Time taken (in seconds) to complete summarization and extraction tasks.
2. **JSON Schema Adherence:** Verification that the LLM returns valid JSON output matching the expected format constraints.
3. **Semantic Accuracy (Double-Defense Check):** Heuristic checks to verify if negation filtering (Layer 1) and action item deduplication (Layer 2) function correctly.

---

## 2. Test Scenario Inventory

The suite runs four distinct, representative scenarios to cover all critical pipelines:

### Scenario 1: Short Sprint Planning (Baseline)
* **Objective:** Validate standard, clean execution.
* **Input:** A simple 5-line discussion assigning two tasks to Bob and Charlie, and one task to Alice.
* **Expectation:** The model extracts exactly 3 action items with correct assignees, deadlines, and priorities, returning a valid JSON structure.

### Scenario 2: Negation & Rejection Filtering (Negation Check)
* **Objective:** Verify the first layer of defense—few-shot negative reasoning.
* **Input:** A transcript where Bob suggests rewriting the database layer in Rust, which Alice and Charlie explicitly turn down ("too high risk", "discard that idea"). Bob then agrees to run PostgreSQL index analysis instead.
* **Expectation:** The suite runs a heuristic check verifying that the task *"rewrite database layer in Rust"* is **excluded** from the output, and only the PostgreSQL optimization task is extracted.

### Scenario 3: Action Item Deduplication (Deduplication Check)
* **Objective:** Verify the second layer of defense—synonym mapping, stemming, and Jaccard token overlap similarity.
* **Input:** Pawan mentions setting up the Redis cache server twice using different phrasing (*"set up the Redis cache server"* and *"Redis database server config"*).
* **Expectation:** The Python post-processing filter (`deduplicate_actions`) intercepts the output and merges these duplicate mentions into a single, clean action item assigned to Pawan.

### Scenario 4: Multilingual Translation & Summarization (Hindi/Hinglish)
* **Objective:** Evaluate multilingual prompt translation quality.
* **Input:** A short transcript containing mixed English and Hindi dialogue (Hinglish) assigning a database backup task.
* **Expectation:** The multilingual engine translates the context and returns the summary and action items localized in Hindi.

---

## 3. Running the Test Suite

Follow these steps to run the test suite on your local system:

### Step 1: Ensure Ollama is running with Mistral
Check that the Ollama local server is active and the `mistral` model is downloaded:
```bash
# Verify Ollama is running and list installed models
ollama list
```
If `mistral:latest` is not present, pull it:
```bash
ollama pull mistral
```

### Step 2: Verify `.env` settings
Ensure your project config is pointing to `mistral`:
```ini
LLM_PROVIDER=ollama
OLLAMA_MODEL=mistral
OLLAMA_SUMMARIZATION_MODEL=mistral
OLLAMA_MULTILINGUAL_MODEL=mistral
OLLAMA_FALLBACK_MODEL=mistral
```

### Step 3: Run the execution command
Run the test script from the project root using the virtual environment interpreter:
```bash
./venv/bin/python performance_test_suite.py
```

---

## 4. Test Suite Outputs & Reports

When you execute the test suite, it performs the following:

1. **Console Logs:** Outputs real-time progress, time elapsed per test case, and structured action items extracted.
2. **Benchmark Report:** Automatically generates a formatted Markdown report in your workspace: `performance_test_results.md`.

### Structure of `performance_test_results.md`
The generated report contains:
* **Inference Latency Table:** A table matching each scenario with its execution time in seconds.
* **Adherence Indicators:** Clear status icons (`✅ PASS` or `❌ FAIL`) for JSON format validity.
* **Detailed Breakdown:** The exact generated summaries, action items, assignees, and priorities returned by the model.
* **Heuristic Evaluation Logs:** Automated check reports flagging whether negation filtering or deduplication checks succeeded or failed during that test run.
