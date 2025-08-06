#!/usr/bin/env python3
"""
Custom Entity Types for Web Trajectory Analysis

This module defines custom Pydantic models for specific entity types
used in web trajectory analysis with Graphiti.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Trajectory(BaseModel):
    """Web trajectory entity representing a complete user navigation session on a platform.
    
    This entity captures the full context of a web agent's trajectory data sequence,
    including the step-by-step actions and code executed during the session.
    """
    
    steps: List[str] = Field(
        description="Ordered list of high-level steps describing the user's actions during the trajectory. "
                   "Each step should be a clear, descriptive action like 'Click Directions button' or 'Enter destination address'."
    )
    
    code_executed: List[str] = Field(
        description="List of actual code/commands executed during the trajectory. "
                   "This includes Playwright commands, API calls, or any programmatic actions taken. "
                   "Example: ['page.click()', 'page.fill()', 'page.keyboard.press()']"
    )

    platform_url: Optional[str] = Field(
        default=None,
        description="The primary platform/website URL where the trajectory took place. "
                   "Example: 'https://maps.google.com'"
    )
    
    final_result: Optional[str] = Field(
        default=None,
        description="The final output or result obtained from completing the trajectory. "
                   "Example: 'Traffic marked as some traffic, 27-minute route'"
    )


# class Platform(BaseModel):
#     """Web platform or service entity where trajectories are executed.
    
#     Represents websites, applications, or services that web agents navigate.
#     """
    
#     official_name: Optional[str] = Field(
#         default=None,
#         description="Official name of the platform or service. Example: 'Google Maps', 'GitHub'"
#     )
    
#     base_url: Optional[str] = Field(
#         default=None,
#         description="Primary URL or domain for the platform. Example: 'https://maps.google.com'"
#     )
    
#     category: Optional[str] = Field(
#         default=None,
#         description="Category or type of platform. Example: 'Maps & Navigation', 'Code Repository', 'E-commerce'"
#     )
    
#     capabilities: List[str] = Field(
#         default_factory=list,
#         description="List of key capabilities or features the platform provides. "
#                    "Example: ['Route planning', 'Traffic analysis', 'Location search']"
#     )


# class TaskType(BaseModel):
    # """Task type entity representing a category of actions or objectives.
    
    # Represents the type of work or goal being accomplished during a trajectory.
    # """
    
    # category: Optional[str] = Field(
    #     default=None,
    #     description="Broad category the task belongs to. Example: 'Navigation', 'Search', 'Booking'"
    # )
    
    # complexity: Optional[str] = Field(
    #     default=None,
    #     description="Complexity level of the task. Values: 'Low', 'Medium', 'High'"
    # )
    
    # typical_steps: List[str] = Field(
    #     default_factory=list,
    #     description="Common steps typically involved in this type of task. "
    #                "Example: ['Enter search query', 'Review results', 'Select option']"
    # )
    
    # success_indicators: List[str] = Field(
    #     default_factory=list,
    #     description="Indicators that show the task was completed successfully. "
    #                "Example: ['Results displayed', 'Confirmation received', 'Data retrieved']"
    # )


class ErrorAttempt(BaseModel):
    """Individual attempt within an error, representing a failed code execution."""
    
    attempt_number: int = Field(
        description="The attempt number (1, 2, 3, etc.)"
    )
    
    code: str = Field(
        description="The Playwright code that was attempted"
    )
    
    error_message: str = Field(
        description="The error message from the attempt"
    )
    
    description: Optional[str] = Field(
        default=None,
        description="Description of what was being attempted"
    )


class Error(BaseModel):
    """Error entity representing a Playwright execution failure and its resolution.
    
    This entity captures information about failed code executions, including
    all attempted solutions and the final successful code (if any).
    """
    
    current_goal: Optional[str] = Field(
        default=None,
        description="The goal being pursued when the error occurred"
    )
    
    description: str = Field(
        description="Description of what was being attempted when the error occurred"
    )
    
    thought: Optional[str] = Field(
        default=None,
        description="LLM's reasoning for the action that led to the error"
    )
    
    successful_code: str = Field(
        description="A string of playwright code that worked to solve the error"
    )
    
    timestamp: str = Field(
        description="When the error occurred (ISO format)"
    )
    
    
    attempted_codes: List[str] = Field(
        description="List of failed attempts in format 'code -> error_message'"
    )


# Dictionary mapping entity type names to their models
# This is what gets passed to Graphiti's add_episode method
WEB_TRAJECTORY_ENTITY_TYPES = {
    'Trajectory': Trajectory,
    'Error': Error,
    # 'ErrorAttempt': ErrorAttempt,
}


def get_entity_types() -> dict[str, BaseModel]:
    """Get the dictionary of custom entity types for web trajectory analysis.
    
    Returns:
        Dictionary mapping entity type names to their Pydantic model classes
    """
    return WEB_TRAJECTORY_ENTITY_TYPES 