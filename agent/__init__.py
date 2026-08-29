"""
google-adk orchestration of the pipeline.

The graph (agent/workflow.py) runs the pipeline's stage functions as
deterministic ADK agents — a SequentialAgent with a ParallelAgent for the two
research stages. Parallel Search is exposed to the reader as an ADK tool
(agent/tools.py); the reading step (agent/reader.py, agent/gemini_reader.py)
is the only LlmAgent on the determination path and its output schema makes
an unsourced fact unrepresentable. agent/test_acceptance.py holds the frozen
RightsResponse fixtures the graph must reproduce exactly.
"""
