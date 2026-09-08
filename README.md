A teacher model that speaks IEC 61131-3 Function Block Diagrams, gained in three gated steps: dataset, pretraining, reinforcement.

The model behind `/fbd` on the taskweft-acp door. It never emits free text: a
grammar admits only the PLCopen subset `taskweft-fbd-compiler` parses, the
compiler and the sandbox label every candidate, and a frozen judge scores the
rest. Constructed rows are ordinary training data; generated rows carry their
model, checkpoint, prompt and grammar hash and live apart from them.

## The three steps

1. `pixi run write-rows` builds the EditScore-shaped corpus (root, candidates,
   scores as three ZStandard parquets), asserting its controls before the emit.
2. `pixi run pretrain` continues pretraining Gemma 4 E2B QAT on the rank1 rows.
3. `pixi run grpo` trains against the compile, run, effect and judge reward.

Every step prints its gate as a table with the floor row beside the result.
