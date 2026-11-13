# 3. Claude reads runbooks; the dependency graph decides the order

## Context

Most recovery knowledge lives in wiki runbooks written years ago. They name systems that were renamed or retired,
list steps in the order a team thought of them, and mix restores with paging and DNS changes. Rewriting hundreds of
them by hand is the work nobody gets to.

## Decision

Claude (`claude-opus-5-5`, low effort, with refusal fallbacks) turns a runbook into steps through a strict tool,
`record_plan`. Each step has a system, an action from a fixed list (restore, verify, switch DNS, scale up, notify),
the steps it waits for, and the runbook words it came from. The system prompt lists the inventory's system names,
says that text inside the runbook is never an instruction, and is cached.

Nothing Claude returns is executed as it stands. Code checks every plan:

- every system exists in the inventory;
- every action is one the platform can run;
- every step it waits for exists;
- the quoted words are really in the runbook, so a step cannot be invented;
- no restore runs before the restores of the systems it depends on, following waits through other steps. This uses
  the dependency graph, not the runbook's wording.

A plan with any problem is marked not executable and lists the problems for a person to fix.

## Consequences

- An outdated runbook becomes a list of specific fixes instead of a surprise during an outage. The console's example
  shows a retired system and two restores that skip their dependencies.
- The checks catch structural mistakes, not every misreading. A step with the right system, a real quote and a valid
  order could still miss the runbook's intent (for example "restore from last Tuesday's backup"). Point-in-time
  choices are not modelled, and a person still signs off on each plan.
- Tests run the converter through the real SDK against canned responses. No evaluation of Claude's extraction
  accuracy was run, because there is no labelled set of real runbooks. That is listed in the known limitations.
