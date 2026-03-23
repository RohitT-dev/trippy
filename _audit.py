import crewai.flow.flow as ff

print("persist available:", "persist" in dir(ff))
print("router available:", "router" in dir(ff))

from crewai.flow.flow import Flow
for m in sorted(dir(Flow)):
    if any(x in m for x in ["remember", "recall", "memory", "persist"]):
        print("Flow class member:", m)

from crewai import Crew
print("\nCrew fields:")
for name, field in Crew.model_fields.items():
    if any(x in name for x in ["task_callback", "cache", "memory"]):
        print(" ", name, ":", field.annotation)

import asyncio
try:
    asyncio.get_running_loop()
    print("\nRunning event loop present")
except RuntimeError:
    print("\nNo running event loop here - asyncio.run() is correct in background thread")


# @router
print("router available:", "router" in dir(ff))

# Flow instance methods
from crewai.flow.flow import Flow, router
from server.src.schema import TravelState

class _F(Flow[TravelState]): pass
f = _F()
for m in sorted(dir(f)):
    if any(x in m for x in ["remember", "recall", "memory", "persist"]):
        print("Flow member:", m, type(getattr(f, m, None)))

# Crew fields
from crewai import Crew
print("\nCrew fields with task/cache/memory:")
for name, field in Crew.model_fields.items():
    if any(x in name for x in ["task_callback", "cache", "memory"]):
        print(" ", name, ":", field.annotation)

# asyncio situation - flow runs in a thread (no event loop)
import asyncio
try:
    loop = asyncio.get_running_loop()
    print("\nRunning event loop:", loop)
except RuntimeError:
    print("\nNo running event loop in this thread — asyncio.run() is correct")
