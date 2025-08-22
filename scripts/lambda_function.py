import asyncio
from .agent import main as patchiq_agent_main

async def run_agent():
    await patchiq_agent_main()

if __name__ == "__main__":
    asyncio.run(run_agent())