# Development & Diagnostic Utilities

This directory contains one-off test scripts and developer tooling used during internal verification and performance benchmarking. They are **not** needed to run or deploy Veridocs.

- **`test_resume_qa.py`**: Integration script that indexes a multi-page resume PDF against a running backend and executes automated queries covering project retrieval, GPA extraction, negative controls ("does he know Kubernetes"), and small-talk conversational bypass.
