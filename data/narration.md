# Student Support Agent: the guided tour

<!-- This file is the single source of the spoken tour. The app reads it and a text-to-speech engine speaks it.
     Edit the words here and the tour changes everywhere. Write numbers as words and avoid symbols so speech sounds natural. -->

## Welcome
Welcome to the Student Support Agent. This is one application that answers student questions, looks up private records through real tools, remembers useful preferences, and asks a human before it changes anything important. Everything you see uses synthetic demonstration data, and the policy handbook is a made-up document, not an official one.

## A real agent, not a chatbot
Every message runs through a bounded agent loop. The model can only propose an action. Application code validates the arguments, checks permissions, runs the tool against the real database, and hands the true result back. The loop is limited to four steps, so it can never run away, and if the language model goes offline, the quick lookup buttons still work without it.

## Five useful tools
The agent has tools for checking your fee status, checking your scholarship status, creating a support request, searching the student policy, and requesting a course change. Each tool has a strict input schema, and unknown fields are rejected instead of ignored, so nobody can smuggle in a hidden identity.

## Honest policy answers
Policy questions are answered from a handbook that is split into labelled chunks. Only the relevant chunks reach the model, and every answer shows which chunk it used. If the handbook does not cover a question, the agent says so and points you to the support desk instead of inventing a rule. A citation guard even removes any source the agent never actually retrieved.

## Memory that knows what to forget
The agent remembers your programme, language, and contact preferences across sessions. A deterministic rule in code, not the model, decides what may be stored. If you paste a password, a one time code, an A P I key, or a card number, nothing from that message is stored, and the secret is hidden before it reaches the model, the traces, or the audit log.

## Identity and privacy
You sign in with a username and password. Passwords are stored only as bcrypt hashes, accounts lock after repeated failures, and the browser holds just a random token. The server works out who you are on every call. You can read your own fee and scholarship records, and nobody else's. Asking for another student's record is blocked in backend code and recorded, no matter what the language model says.

## A human approves sensitive changes
When you ask to change your course, the agent only creates a pending request. Nothing changes until an approver reviews it. The approver sees the proposed change, its consequences, and a risk advisor that explains why a request looks low, medium, or high risk. The advisor never decides anything. A rejected, expired, stale, duplicate, or failed request can never execute, and a failure rolls everything back.

## An audit trail you can verify
Every important action is written to an append only audit log, with who did it, what was attempted, whether it was allowed, and the final result. On top of the database protections, every event is chained to the one before it with a cryptographic hash. One click verifies the chain, and any edited or deleted row is detected, even if someone removes the database triggers.

## We attack our own agent
Our red team lab replaces the language model with a hostile one that tries fifteen attacks, including cross student reads, smuggled admin fields, injection strings, fake privileged tools, oversized payloads, floods, and memory poisoning. All fifteen are blocked, and tests prove the lab notices when a control is deliberately broken. The security lives in code, not in prompts.

## Honest evaluation
Every number in our reports comes from tests that actually ran, on isolated databases, compared against a baseline taken from the first milestone. Tokens the provider does not report are shown as unavailable, never invented, and results from the offline mock model are labelled as mock. Over a hundred automated tests back the claims.

## What makes this different
Most student agents rely on a prompt that says please do not leak data. This one assumes the model can be fully compromised, and proves that private data stays private, that sensitive actions wait for a human, and that the evidence cannot be quietly rewritten. Thank you for listening, and enjoy exploring.
