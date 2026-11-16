import asyncio
import httpx

async def main():
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.jarvisclaw.ai/v1/chat/completions",
                json={
                    "model": "auto/free",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with OK"
                        }
                    ],
                    "max_tokens": 20
                },
                headers={
                    "Content-Type": "application/json"
                }
            )

            print("STATUS:", response.status_code)
            print("RESPONSE:", response.text[:1000])

    except Exception as error:
        print("ERROR TYPE:", type(error).__name__)
        print("ERROR DETAILS:", repr(error))

asyncio.run(main())