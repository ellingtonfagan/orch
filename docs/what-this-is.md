# ORCH, in plain language

## The blurb

I gave AI agents access to my machine for six months. They ran nearly six thousand commands across
sixteen projects — writing files, installing packages, calling APIs, sending mail, pushing code.
I approved almost none of it individually, because nobody can.

ORCH reads the logs those agents left behind and tells me what they actually touched. Not whether
they did good work; **what they could have broken if they had gone wrong.** It compares that
against a list of what I said they were allowed to touch, and reports the gap.

The first time I ran it, it found a live API key sitting in plain text in a log file, referenced over a thousand
times by a single agent.

## The one-sentence version

ORCH is a flight recorder for AI agents: it reads what your agents already did and tells you how
much damage they were in a position to cause.

## Why it exists

The usual question about an AI system is *"is this model safe?"* That question has no answer you
can enforce. It is a property of something you did not build and cannot inspect.

The better question is *"what can this thing reach?"* — and that one is answerable, because reach
is a property of the machine, not the model. Files it can write. Networks it can call. Credentials
sitting in its environment. Commands it can run that cannot be undone.

The failure that makes this urgent had no attacker in it. Last summer a coding agent deleted a
production database during a code freeze. No exploit, no break-in. **It simply had access it did
not need, and used it.** Unpredictable is not the same as malicious, and it is just as expensive.

## What it actually does, in order

**1. It reads the logs agents already leave behind.**
Every session with Claude Code or Codex writes a transcript to disk. Nobody reads them; they are
enormous. ORCH reads all of them.

**2. It turns each action into a plain fact.**
Not "the agent was working on the auth module" — *this command wrote to this file*, *this one
called this web address*, *this one referenced this password variable*. No interpretation, no
opinion. Just what happened.

**3. It checks each fact against a list you wrote.**
The list says which folders may be written to, which internet addresses may be contacted, which
outside services may be used. Anything not on the list counts as a violation. The default is no:
if you did not name it, it does not pass.

**4. It scores how bad each violation is.**
This part is deliberately yours, not mine and not the machine's. Whether a leaked password matters
more than forty unknown web addresses is a judgement about *your* risk, and a tool that makes it
for you is guessing.

**5. It reports what each session could have reached.**
Per session: the worst thing it did, how many *different kinds* of access it held, and how many
violations. The count of different kinds is the number that matters — an agent holding four
separate powers can combine them in ways nobody reviewed.

**6. It says what it cannot see.**
Every report ends with its own blind spots. A tool that hides its limits is worse than no tool,
because you will trust it.

## Who it is for

Anyone who has given an AI agent real access and cannot now say what it did with it. In practice
that is a small team running coding agents, or one person running several.

It is not for someone deciding whether to *adopt* agents. It is for someone who already has, and
has lost track.

## What it deliberately does not do

**It does not block anything.** It reads history; it never stands between an agent and its work.
Live blocking is a solved product and several companies sell it.

**It does not judge code quality.** Whether the agent wrote good code is a different question with
different tools.

**It does not decide what is acceptable.** It reports the gap between what happened and what you
declared. Declaring is your job.

**It does not phone home.** Everything runs locally, against files already on your machine. It has
no server and sends nothing anywhere. Given that its input is logs containing live credentials,
that is not a feature; it is the only defensible design.

## The honest limitation

ORCH reads what agents *recorded*, and agents only record what they did through their own tools.
If an agent runs a script and that script writes a file, the file was written and the log does not
say so.

**So the tool has the same weakness as the thing it audits: it reads the report, not the world.**
I know that failure personally. I once spent six days and seventeen commits watching a status file
that said my trading bot was frozen. It was not frozen. The status file was stale, and the answer
was sitting in a log on the same machine the whole time. The monitor was observing the monitor.

The fix is not to trust the logs harder. It is to add a second, independent check that looks at the
machine itself — what actually changed on disk — and to treat *disagreement between the two* as the
finding. When the repository changed and no agent action explains it, that is the interesting
sentence in the whole report.

That check is being built. Until it exists, this tool tells you about the reach it can see, and
says so.

## What it costs to be wrong about this

The tools are cheap and the logs are already written. What is expensive is the year spent believing
a clean report from a check that could not fail. The gap between an agent you supervise and an
agent you merely host is not visible from the outside, and right now most people cannot tell you
which one they are running.
