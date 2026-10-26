# Vector graphs for agent memory

How a vector graph could help agents retain memory and share it across models and GPUs, and where it does not help. The key point: "memory" means two different things, and a vector graph only helps with one of them.

## Two kinds of memory

### 1. The model's working memory (the KV cache)

This is what John's engine (zend) and vLLM's tiered offloading manage: the model's internal state from having read a conversation.

- **Fast.** Reloading it skips re-reading the conversation.
- **Locked to one model.** It only works with that exact model and weights, and only for exactly the same text in the same order. Qwen's KV is useless to Llama, and even to a different quantisation of Qwen.
- **Shareable only between identical models.** If many GPUs run the same model, they can share blocks for identical text, such as a shared system prompt or the same repo files. That's what content-addressed caching does.

### 2. Knowledge memory (where a vector graph lives)

This is what was learned, stored as text plus "embeddings": a numeric fingerprint of meaning, so you can search by similarity. The graph part adds links between items, for example "this function → this bug → this fix → this agent's session."

- **Model-agnostic.** It's just text, so any model on any GPU can read it, including a different model, a newer version, or a frontier model.
- **Durable.** It survives restarts, replacing a model, or an agent finishing.
- **Not free to use.** Whatever is retrieved still has to be read by the model, so it costs prefill compute. It saves thinking, not reading.

## How it helps retention

Instead of keeping a 60K-token conversation alive in GPU memory, an agent could:

1. write down the useful facts as it works ("the bug is in `separable.py`", "the tests are run with `pytest -k foo`", "already tried X, it failed");
2. drop the bulky history;
3. pull back only the relevant pieces when needed.

That gives shorter contexts, less GPU memory per agent, and therefore more agents per card. It might also help the looping measured in the agent benchmarks, since "already tried this command, it failed" is exactly the kind of note that stops an agent repeating itself.

## How it helps sharing

- **Between agents:** agent 7 discovers how a repo's test setup works, and agent 12 on another node finds that note instead of rediscovering it.
- **Between models:** a cheap local model can do the exploration and leave notes, and a frontier model picks up the hard part already briefed. The reverse works too.
- **Between GPUs and nodes:** it sits on ordinary storage or CPU nodes, not in GPU memory, so locality matters far less than it does for KV.

## The research angle

The graph could also steer the KV tier rather than replace it. Index which KV blocks belong to which files, tasks and agents, then predict what an agent will need next and prefetch it from NVMe before it asks. That's close to CacheScout's idea and to zend's provenance-selected attention, and it fits an agent-level Markov layer: the graph's edges are the transitions.

## The catches

- **Retrieval can miss**, and then the agent works without the fact it needed.
- **Notes go stale.** A fix made by one agent changes the code another agent's note describes.
- **Concurrent writers** need some rules for consistency.
- **Everyone must use the same embedding model**, or the fingerprints don't match.
- **Access boundaries** matter as soon as more than one group's agents share a store.
