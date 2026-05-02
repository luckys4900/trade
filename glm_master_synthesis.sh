#!/bin/bash

# GLM Master AI Synthesis Script
# 10並列エージェント出力を統合・最適化

set -e

# Setup
export ZAI_API_KEY="e7efefc0da5c49a9a684297efd193305.KawyRIk4RgAPEKXE"

RESULTS_DIR="results"
OUTPUT_FILE="results/master_synthesis.json"

echo "🤖 GLM Master AI Synthesis Started"
echo "=================================="

# Verify agent outputs exist
if [ ! -d "$RESULTS_DIR" ]; then
    echo "❌ ERROR: $RESULTS_DIR not found. Run agents first."
    exit 1
fi

AGENT_COUNT=$(ls -1 $RESULTS_DIR/agent-*.json 2>/dev/null | wc -l)
echo "✓ Found $AGENT_COUNT agent outputs"

if [ "$AGENT_COUNT" -lt 10 ]; then
    echo "⚠️  WARNING: Expected 10 agents, found $AGENT_COUNT"
fi

# Build synthesis prompt
SYNTHESIS_PROMPT=$(cat <<'PROMPT'
You are the Master AI synthesizing multi-agent analysis results.

[TASK]
1. Read all agent output files in results/ directory
2. Merge and validate outputs
3. Detect conflicts and contradictions
4. Generate unified strategy with optimization recommendations
5. Validate statistical significance

[OUTPUT FORMAT - RETURN VALID JSON ONLY]
{
  "synthesis_timestamp": "ISO_TIMESTAMP",
  "agents_processed": NUMBER,
  "total_candidates_unique": NUMBER,
  "final_candidates": [
    {
      "rank": 1,
      "ticker": "STRING",
      "composite_score": FLOAT,
      "ev": FLOAT,
      "rrr": FLOAT,
      "entry": FLOAT,
      "stop": FLOAT,
      "target": FLOAT,
      "backtest_sample_size": NUMBER,
      "win_rate": FLOAT,
      "sharpe_ratio": FLOAT,
      "confidence": FLOAT (0-1)
    }
  ],
  "optimization_recommendations": ["STRING"],
  "quality_checks": {
    "all_agents_completed": BOOL,
    "no_critical_conflicts": BOOL,
    "statistical_validity": BOOL,
    "implementation_ready": BOOL,
    "warnings": ["STRING"]
  },
  "token_usage_summary": {
    "synthesis_tokens": NUMBER,
    "estimated_cost": "STRING"
  }
}

Return ONLY valid JSON - no markdown, no explanation.
PROMPT
)

# Execute GLM synthesis
echo ""
echo "Calling GLM Master AI..."
echo "========================"

opencode run "$SYNTHESIS_PROMPT" \
    --model "zai-coding-plan/glm-5-turbo" \
    2>&1 | tee "$OUTPUT_FILE"

echo ""
echo "✓ Synthesis complete: $OUTPUT_FILE"
echo "=================================="

# Validate output
if [ -f "$OUTPUT_FILE" ]; then
    if jq empty "$OUTPUT_FILE" 2>/dev/null; then
        echo "✓ Output JSON is valid"
        READY=$(jq -r '.quality_checks.implementation_ready' "$OUTPUT_FILE")
        echo "✓ Implementation ready: $READY"
    else
        echo "❌ Output JSON is invalid"
        exit 1
    fi
else
    echo "❌ No output file created"
    exit 1
fi
