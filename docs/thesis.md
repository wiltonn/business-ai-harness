# Thesis

## Claim under test

Complex business tasks become **cheaper, more reliable, more governable, more observable, more
testable, and more maintainable** when they are decomposed into **explicit, typed decisions**
embedded inside **domain-specific execution harnesses**, rather than handed to a single
unconstrained agent.

## What a harness is

A harness is a domain-specific program that composes:

| Component | Role |
|---|---|
| Deterministic code | everything that can be computed (parsing, timing, validation) |
| Bounded decisions | small typed choices (KEEP/REMOVE, DUPLICATE/DISTINCT, score 1–5) |
| Foundation-model reasoning | open-ended understanding, structure, ambiguity resolution |
| Domain context & business rules | what "good" means here |
| Workflow state | where we are, what's done, what's pending |
| Policies | what is allowed, what must escalate |
| Tools / execution providers | systems that act (MakeMyClip, Salesforce, Jira…) |
| Artifact providers | systems that generate specialized outputs (HyperFrames, report engines) |
| Verification | did the expected result occur? |
| Escalation & human review | consequential ambiguity goes to a person |
| Observability | a trace of every decision and action |
| Evaluation | measured quality, cost, reliability vs. baselines |
| Learning from corrections | human decisions become precedent, then rules |

## The general separation

> **Decision providers decide. Execution providers act. Artifact/graphics providers generate
> specialized artifacts. Verification providers check. Humans handle consequential ambiguity.**

The same shape should transfer across domains:

| Role | Video experiment | Other domains |
|---|---|---|
| Decision provider | rules / Jev / Claude / human | rules / Jev / Claude / human |
| Execution provider | MakeMyClip, Resolve | Salesforce, SAP, Jira, an API |
| Artifact provider | HyperFrames, MMC drawtext | document engine, reporting engine, deck generator |
| Verification | render checks, AI review, human review | reconciliation, schema checks, approvals |

## Learning loop

```
UNKNOWN → HUMAN DECISION → PRECEDENT → REPEATED PRECEDENT
        → PROPOSED RULE → VALIDATED RULE → DETERMINISTIC KNOWLEDGE
```

Every human correction should be capturable as structured data that can move a decision type
down this ladder — from expensive/uncertain toward cheap/deterministic.

## What would falsify it (for the video experiment)

- The decomposed harness is not meaningfully better than Claude directly driving MakeMyClip on
  quality, mistakes, or human revision effort, **and** costs more to build and run.
- Bounded decisions are so context-dependent that they collapse back into one big prompt.
- The trace/plan overhead doesn't make errors easier to find or fix.

We are explicitly allowed to conclude "the separation is not worth it here."

## Provider independence

Jev is a leading candidate for the bounded-decision layer, but every decision is coded against a
provider interface so that a rule, a small model, Jev, Claude, or a human can be swapped and
compared on the same decision type.
