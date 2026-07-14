"""
AI Agent — the ReAct (Reasoning + Acting) loop.

This is the most important file in the entire project.
It implements autonomous investigation of network incidents.

ReAct Pattern Explained:
    Traditional code: IF latency > 300ms THEN create_ticket()
    ReAct Agent:      Observe alert → Think: what data do I need? →
                      Act: call tools → Observe results → Think: what does this mean? →
                      Act: call more tools or conclude → Final answer

Why ReAct over simple rule-based?
- Rules are rigid: "latency > 300ms → CRITICAL"
- ReAct reasons: "latency is 450ms on R1, but S1 (neighbor) is also degraded,
  and health score is 60 — this is a cascading failure from R1's upstream link,
  not an isolated issue. Root cause: congestion on R1↔R2 interconnect."
- Rules can't detect cascading failures. ReAct can.

Loop Safety:
- MAX_ITERATIONS cap prevents infinite tool-calling loops
- Timeout ensures agent concludes within SLA
- JSON output parsing with fallback for malformed responses
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from services.ai_agent.groq_client import GroqLLMClient, GroqClientError
from services.ai_agent.tools import GROQ_TOOL_DEFINITIONS, execute_tool
from services.ai_agent.prompts import SYSTEM_PROMPT, build_alert_context

logger = structlog.get_logger(__name__)


# -----------------------------------------------
# Agent Configuration
# -----------------------------------------------
MAX_ITERATIONS = 8          # Max tool calls before forcing conclusion
AGENT_TIMEOUT_SECONDS = 60  # Max wall-clock time for one investigation


# -----------------------------------------------
# Data Classes
# -----------------------------------------------

@dataclass
class AgentResult:
    """
    Structured output from the AI Agent after completing investigation.
    This is what gets published to Kafka network.actions topic.
    """
    alert_id: str
    device_id: str
    root_cause: str
    confidence_score: float
    affected_devices: List[str]
    is_cascading: bool
    severity_assessment: str
    immediate_action: str
    investigation_summary: str

    # Metadata
    iterations_used: int = 0
    tool_calls_made: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "device_id": self.device_id,
            "root_cause": self.root_cause,
            "confidence_score": self.confidence_score,
            "affected_devices": self.affected_devices,
            "is_cascading": self.is_cascading,
            "severity_assessment": self.severity_assessment,
            "immediate_action": self.immediate_action,
            "investigation_summary": self.investigation_summary,
            "iterations_used": self.iterations_used,
            "tool_calls_made": self.tool_calls_made,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error_message": self.error_message,
        }

    def to_kafka_payload(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class FailedAgentResult(AgentResult):
    """Represents a failed investigation — still contains partial info."""
    success: bool = False


# -----------------------------------------------
# Core Agent
# -----------------------------------------------

class NetworkInvestigationAgent:
    """
    AI Agent that investigates network incidents using the ReAct pattern.

    Usage:
        agent = NetworkInvestigationAgent(groq_client)
        result = agent.investigate(alert_data)
    """

    def __init__(self, groq_client: GroqLLMClient):
        self._groq = groq_client

    def investigate(self, alert_data: Dict[str, Any]) -> AgentResult:
        """
        Run a full investigation on a network alert using ReAct loop.

        The loop:
        1. Build initial context from alert
        2. Call Groq with tools available
        3. If model calls tools → execute → send results back
        4. Repeat until model produces final JSON answer (no tool calls)
        5. Parse JSON → return AgentResult

        Args:
            alert_data: Alert dict from Kafka (deserialized Alert model)

        Returns:
            AgentResult with root_cause, confidence, recommendation, etc.
        """
        alert_id = alert_data.get("alert_id", "unknown")
        device_id = alert_data.get("device_id", "unknown")
        start_time = time.time()

        logger.info(
            "agent.investigation_started",
            alert_id=alert_id,
            device_id=device_id,
            alert_type=alert_data.get("alert_type"),
            severity=alert_data.get("severity"),
        )

        # Build conversation history starting with system prompt
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_alert_context(alert_data)},
        ]

        iterations = 0
        tool_calls_made = 0

        try:
            # -----------------------------------------------
            # ReAct Loop
            # -----------------------------------------------
            while iterations < MAX_ITERATIONS:
                # Check wall-clock timeout
                elapsed = time.time() - start_time
                if elapsed > AGENT_TIMEOUT_SECONDS:
                    logger.warning(
                        "agent.timeout",
                        alert_id=alert_id,
                        elapsed_seconds=round(elapsed, 2),
                    )
                    break

                iterations += 1

                logger.debug(
                    "agent.react_iteration",
                    alert_id=alert_id,
                    iteration=iterations,
                    message_count=len(messages),
                )

                # Call Groq LLM
                response = self._groq.chat(
                    messages=messages,
                    tools=GROQ_TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.1,   # Low temp = deterministic reasoning
                )

                response_message = response.choices[0].message
                finish_reason = response.choices[0].finish_reason

                # Add assistant response to conversation history
                messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in (response_message.tool_calls or [])
                    ] or None,
                })

                # -----------------------------------------------
                # Case 1: Model wants to call tools → execute them
                # -----------------------------------------------
                if response_message.tool_calls:
                    for tool_call in response_message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_calls_made += 1

                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}

                        logger.info(
                            "agent.tool_call",
                            alert_id=alert_id,
                            tool=tool_name,
                            args=tool_args,
                            call_number=tool_calls_made,
                        )

                        # Execute the tool
                        tool_result = execute_tool(tool_name, tool_args)

                        # Add tool result to conversation
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result,
                        })

                    # Continue the loop — model will reason on tool results
                    continue

                # -----------------------------------------------
                # Case 2: Model produced final answer (no tool calls)
                # -----------------------------------------------
                final_text = response_message.content or ""

                duration = round(time.time() - start_time, 2)

                logger.info(
                    "agent.investigation_complete",
                    alert_id=alert_id,
                    iterations=iterations,
                    tool_calls=tool_calls_made,
                    duration_seconds=duration,
                    finish_reason=finish_reason,
                )

                # Parse the JSON conclusion from model's response
                result = self._parse_conclusion(
                    text=final_text,
                    alert_id=alert_id,
                    device_id=device_id,
                    iterations=iterations,
                    tool_calls=tool_calls_made,
                    duration=duration,
                )

                return result

            # -----------------------------------------------
            # Loop exhausted (max iterations or timeout)
            # Force a conclusion with what we have
            # -----------------------------------------------
            logger.warning(
                "agent.max_iterations_reached",
                alert_id=alert_id,
                iterations=iterations,
                tool_calls=tool_calls_made,
            )

            duration = round(time.time() - start_time, 2)

            return AgentResult(
                alert_id=alert_id,
                device_id=device_id,
                root_cause=f"Investigation incomplete — exceeded {MAX_ITERATIONS} iterations. Manual review required.",
                confidence_score=0.3,
                affected_devices=[device_id],
                is_cascading=False,
                severity_assessment=alert_data.get("severity", "CRITICAL"),
                immediate_action="Manually investigate this device. AI agent could not conclude.",
                investigation_summary=f"Agent ran {iterations} iterations and {tool_calls_made} tool calls but could not produce a final conclusion within the iteration limit.",
                iterations_used=iterations,
                tool_calls_made=tool_calls_made,
                duration_seconds=duration,
                success=False,
                error_message="Max iterations reached",
            )

        except GroqClientError as e:
            duration = round(time.time() - start_time, 2)
            logger.error(
                "agent.groq_error",
                alert_id=alert_id,
                error=str(e),
                duration_seconds=duration,
            )
            return AgentResult(
                alert_id=alert_id,
                device_id=device_id,
                root_cause="AI investigation failed due to LLM API error. Manual review required.",
                confidence_score=0.0,
                affected_devices=[device_id],
                is_cascading=False,
                severity_assessment=alert_data.get("severity", "CRITICAL"),
                immediate_action=f"Manual investigation required. AI error: {str(e)[:100]}",
                investigation_summary="AI Agent could not complete investigation due to Groq API error.",
                iterations_used=iterations,
                tool_calls_made=tool_calls_made,
                duration_seconds=duration,
                success=False,
                error_message=str(e),
            )

    # -----------------------------------------------
    # Private: JSON Conclusion Parser
    # -----------------------------------------------

    def _parse_conclusion(
        self,
        text: str,
        alert_id: str,
        device_id: str,
        iterations: int,
        tool_calls: int,
        duration: float,
    ) -> AgentResult:
        """
        Extract and parse the JSON conclusion from the agent's final response.

        The agent is instructed to produce:
        ```json
        { "root_cause": "...", "confidence_score": 0.85, ... }
        ```

        We extract the JSON block using regex and parse it.
        If parsing fails, we return a partial result with the raw text.
        """
        # Try to extract JSON from ```json ... ``` code block
        json_pattern = r"```json\s*([\s\S]*?)\s*```"
        match = re.search(json_pattern, text, re.IGNORECASE)

        raw_json = None
        if match:
            raw_json = match.group(1).strip()
        else:
            # Fallback: try to find a raw JSON object in the text
            brace_pattern = r"\{[\s\S]*\}"
            brace_match = re.search(brace_pattern, text)
            if brace_match:
                raw_json = brace_match.group(0).strip()

        if not raw_json:
            logger.warning(
                "agent.conclusion_parse_failed",
                alert_id=alert_id,
                reason="No JSON block found in response",
                response_preview=text[:200],
            )
            # Return partial result using raw text as root cause
            return AgentResult(
                alert_id=alert_id,
                device_id=device_id,
                root_cause=text[:500] if text else "No conclusion produced",
                confidence_score=0.4,
                affected_devices=[device_id],
                is_cascading=False,
                severity_assessment="CRITICAL",
                immediate_action="Review AI investigation logs for full analysis",
                investigation_summary="AI Agent produced analysis but not in expected JSON format.",
                iterations_used=iterations,
                tool_calls_made=tool_calls,
                duration_seconds=duration,
                success=False,
                error_message="Could not parse JSON conclusion",
            )

        try:
            conclusion = json.loads(raw_json)

            logger.info(
                "agent.conclusion_parsed",
                alert_id=alert_id,
                confidence=conclusion.get("confidence_score"),
                is_cascading=conclusion.get("is_cascading"),
                affected_count=len(conclusion.get("affected_devices", [])),
            )

            return AgentResult(
                alert_id=alert_id,
                device_id=device_id,
                root_cause=conclusion.get("root_cause", "Root cause undetermined"),
                confidence_score=float(conclusion.get("confidence_score", 0.5)),
                affected_devices=conclusion.get("affected_devices", [device_id]),
                is_cascading=bool(conclusion.get("is_cascading", False)),
                severity_assessment=conclusion.get("severity_assessment", "CRITICAL"),
                immediate_action=conclusion.get("immediate_action", "Investigate manually"),
                investigation_summary=conclusion.get("investigation_summary", ""),
                iterations_used=iterations,
                tool_calls_made=tool_calls,
                duration_seconds=duration,
                success=True,
            )

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                "agent.json_decode_failed",
                alert_id=alert_id,
                error=str(e),
                raw_json_preview=raw_json[:200],
            )
            return AgentResult(
                alert_id=alert_id,
                device_id=device_id,
                root_cause=f"Partial analysis: {text[:300]}",
                confidence_score=0.3,
                affected_devices=[device_id],
                is_cascading=False,
                severity_assessment="CRITICAL",
                immediate_action="Manual investigation required — AI produced malformed output",
                investigation_summary="AI Agent completed investigation but JSON output was malformed.",
                iterations_used=iterations,
                tool_calls_made=tool_calls,
                duration_seconds=duration,
                success=False,
                error_message=f"JSON parse error: {str(e)}",
            )
