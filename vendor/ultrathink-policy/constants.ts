/**
 * Programming Desk overrides for the VPS claude-ultrathink engine.
 *
 * The engine is not in this repository. These constants are what LEAD skills
 * and a later VPS patch must use. They replace src/think/types.ts defaults.
 *
 * Do not lower MIN_NODES below 5 for a real build task.
 * Do not raise MAX_NODES above 8.
 * CoT steps are 4–8 per node (each step → one Linear sub-issue).
 * CoT fill stays sequential unless the runtime can parallelize safely.
 */

export const MIN_NODES = 5;
export const MAX_NODES = 8;

/** Numbered rationale steps per node. Each step becomes one Sub-Issue. */
export const MIN_STEPS = 4;
export const MAX_STEPS = 8;

/** Rationale budget sized for MAX_STEPS one-to-two-sentence steps (~250 chars each). */
export const MAX_RATIONALE_CHARS = 2000;

/** Desk default. Upstream runThink already defaults concurrency to 1. */
export const COT_CONCURRENCY_DEFAULT = 1;

export const LINEAR_DENSITY_DEFAULT = "dense" as const;

/** Set on the Notion Task when Cursor Cloud Agents execute the work. */
export const NOTION_AGENT_CURSOR = "cursor-cloud";

export const NOTION_AGENT_TASK_GRAPH =
	"collection://be3418f0-d2d8-411b-8677-fa8a95ee63be";

export const LINEAR_TEAM_DEFAULT = "Spectrum Web Co";

/**
 * Fallback graph used only when GoT generation fails.
 * Five nodes: meets MIN_NODES. Not a license to skip regeneration
 * when the model simply returned too few nodes.
 */
export const FALLBACK_NODE_COUNT = 5;
