"""
google-adk orchestration of the pipeline.

The graph (agent/workflow.py) reuses pipeline/ step functions as
FunctionNodes; sources and the rules engine are exposed as ADK tools
(agent/tools.py); the reading step (agent/reader.py) is the only LlmAgent
on the determination path and its output schema makes an unsourced fact
unrepresentable. agent/test_acceptance.py holds the frozen RightsResponse
fixtures the graph must reproduce exactly.
"""
