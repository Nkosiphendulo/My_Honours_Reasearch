"""Simulate a full SPC conversation using src.llm to validate flow and timing estimates.

This script does a deterministic, non-interactive run through a sample conversation,
measuring the number of turns and estimating human response times to verify the
whole exchange can fit within 10-15 minutes.
"""

from time import perf_counter
from src.llm import chat_spc, generate_final_spc

# Sample conversation: user and assistant turns
messages = [
    {"role": "assistant", "message": "Hi — tell me about a campus need you'd like to explore."},
    {"role": "user", "message": "I'd like an idea to help students find quiet study spaces on campus when the library is full."},
]

start = perf_counter()
# Assistant asks clarifying questions
res = chat_spc(messages, username="student")
messages.append({"role": "assistant", "message": res.get("reply", "")})
# Simulate user answers to two clarifying Qs
messages.append({"role": "user", "message": "Main users are undergraduates and postgrads. They should be able to see available rooms, reserve a short slot, and get email confirmations."})
res = chat_spc(messages, username="student")
messages.append({"role": "assistant", "message": res.get("reply", "")})
# User accepts suggestions and requests final SPC generation
messages.append({"role": "user", "message": "Sounds good — please generate the SPC."})
res = chat_spc(messages, username="student")
messages.append({"role": "assistant", "message": res.get("reply", "")})
# Simulate user confirmation
messages.append({"role": "user", "message": "yes"})
final = generate_final_spc(messages, username="student", participant_code="anon-1234")
end = perf_counter()

# Estimate human timing: assume user reads and replies in 60-90s per user turn, assistant replies are immediate.
user_turns = sum(1 for m in messages if m.get("role")=="user")
# Use a conservative average of 150s per user response to reflect thoughtful answers
estimated_seconds = user_turns * 150  # average 150s per user response

print("Simulated turns:", len(messages))
print("User turns:", user_turns)
print("Estimated human time (s):", estimated_seconds)
print("Estimated human time (min):", round(estimated_seconds/60, 1))
print("Estimated fits in 10-15 min?:", 600 <= estimated_seconds <= 900)
print("Final SPC overview (traced):")
print(final.get("overview"))
print("---")
print("Functional requirements:")
for fr in final.get("functional_requirements", []):
    print(f"- {fr.get('id')}: {fr.get('text')}")

print("--- Simulation time elapsed (script):", round(end-start, 3), "seconds")
