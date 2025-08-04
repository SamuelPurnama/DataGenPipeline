# Trajectory Context Feature

## Overview

The trajectory pipeline now includes a **Trajectory Context** feature that fetches relevant past trajectories from the Graphiti knowledge graph to provide context for LLM calls. This helps the LLM see how similar tasks were accomplished before, improving its planning performance.

## How It Works

### 1. **Platform & Task Type Extraction**
For each instruction, the system automatically extracts:
- **Platform**: The website/platform being used (e.g., "Google Calendar", "Google Maps")
- **Task Type**: The type of action being performed (e.g., "Schedule Event", "Search Location")

### 2. **Trajectory Search**
The system searches the Graphiti knowledge graph for:
- **Relevant Episodes**: Past trajectory executions with similar goals
- **Trajectory Entities**: Specific trajectory nodes that match the current task

### 3. **Context Integration**
The found trajectories are formatted and included in the LLM prompt, providing:
- Historical context of how similar tasks were accomplished
- Step-by-step approaches that worked before
- Platform-specific patterns and strategies

## Configuration

### Environment Variables
Set these environment variables to connect to your Graphiti database:

```bash
export GRAPHITI_URI="bolt://localhost:7687"
export GRAPHITI_USER="neo4j"
export GRAPHITI_PASSWORD="your_password"
```

### Graphiti Group ID
The system uses a default group ID of `"trajectory_context"` for organizing trajectory data. You can modify this in the pipeline configuration.

## Usage

### Running with Trajectory Context
The feature is automatically enabled when Graphiti is available. The pipeline will:

1. **Extract** platform and task type from each instruction
2. **Search** for relevant past trajectories
3. **Include** the context in LLM prompts
4. **Log** the results for monitoring

### Example Output
```
🏷️ Platform: Google Calendar, Task Type: Schedule Event
🔍 Fetching relevant past trajectories...
✅ Found relevant past trajectories
=== RELEVANT PAST TRAJECTORIES ===
Found 3 relevant past trajectories for: Schedule a meeting with John tomorrow at 2pm
Platform: Google Calendar, Task Type: Schedule Event

--- Past Trajectory 1 ---
Name: Trajectory calendar_abc123
Created: 2024-01-15T10:30:00
Source: Trajectory entity
Content: Successfully scheduled a meeting with Sarah on January 16th at 3pm. Used the "+" button to create new event, filled in title, date, time, and attendee email...
=== END PAST TRAJECTORIES ===
```

## Testing

### Test Script
Run the test script to verify the functionality:

```bash
python test_trajectory_context.py
```

This will test:
- Platform and task type extraction
- Trajectory context fetching
- Error handling

### Expected Test Results
```
🧪 Testing Trajectory Context Functionality
==================================================

📋 Test Case 1:
Instruction: Schedule a meeting with John tomorrow at 2pm
URL: https://calendar.google.com
Extracted Platform: Google Calendar
Extracted Task Type: Schedule Event
✅ Platform extraction: PASS
✅ Task type extraction: PASS

🔍 Fetching trajectory context for: Schedule a meeting with John tomorrow at 2pm
✅ Trajectory context fetched successfully
Context length: 1250 characters
Context preview:
=== RELEVANT PAST TRAJECTORIES ===
...
```

## Benefits

### 1. **Improved LLM Performance**
- LLM sees how similar tasks were successfully completed
- Reduces trial-and-error in action planning
- Learns from past successful strategies

### 2. **Platform-Specific Learning**
- Understands platform-specific UI patterns
- Learns common interaction sequences
- Adapts to platform quirks and features

### 3. **Task-Specific Context**
- Provides relevant examples for specific task types
- Shows successful approaches for similar goals
- Reduces failure rates on familiar tasks

### 4. **Continuous Improvement**
- As more trajectories are added to the graph, context quality improves
- System learns from successful and failed attempts
- Builds a knowledge base of effective strategies

## Troubleshooting

### Common Issues

1. **Graphiti Connection Failed**
   ```
   ❌ Error fetching trajectory context: Connection refused
   ```
   - Check if Graphiti database is running
   - Verify environment variables are set correctly
   - Ensure network connectivity

2. **No Trajectories Found**
   ```
   ℹ️ No relevant past trajectories found
   ```
   - This is normal if no similar trajectories exist yet
   - The system will work without context
   - As you run more trajectories, context will become available

3. **Import Errors**
   ```
   ⚠️ Graphiti not available. Trajectory context will be disabled.
   ```
   - Install Graphiti dependencies
   - Check Python path includes Graphiti modules
   - Feature will work without Graphiti (just without context)

### Debug Mode
To see detailed trajectory context in logs, the system prints:
- Platform and task type extraction
- Number of trajectories found
- Preview of context being sent to LLM

## Integration with Existing Pipeline

The trajectory context feature is **backward compatible**:
- Works with existing pipeline without changes
- Gracefully handles missing Graphiti setup
- Doesn't affect pipeline performance when disabled
- Can be easily enabled/disabled via configuration

## Future Enhancements

### Planned Features
1. **Context Quality Scoring**: Rank trajectory relevance
2. **Adaptive Context Length**: Adjust based on task complexity
3. **Cross-Platform Learning**: Learn patterns across different platforms
4. **Failure Analysis**: Learn from failed trajectories
5. **Context Caching**: Cache frequently used contexts for performance

### Customization Options
- Configurable search queries
- Adjustable context length limits
- Custom platform/task type mappings
- Filtering by success rate or date range 