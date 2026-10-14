"""Checks that your API key works and lists the models you can use."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")
base, key, model = os.getenv("OPENAI_BASE_URL"), os.getenv("OPENAI_API_KEY"), os.getenv("MODEL", "gpt-4o-mini")
if not key:
    raise SystemExit("Fill in OPENAI_BASE_URL and OPENAI_API_KEY in the .env file first.")

client = OpenAI(base_url=base or None, api_key=key,
                default_headers={"x-portkey-api-key": key} if base and "portkey" in base else None)
print(f"Gateway: {base or 'OpenAI default'}\n")
try:
    ids = sorted(m.id for m in client.models.list())
    print("Models you can use:")
    for i in ids:
        print("  ", i)
except Exception as e:
    print(f"Couldn't list models ({e}). That's OK if the chat test below works.")

print(f"\nTesting a reply from {model} ...")
try:
    r = client.chat.completions.create(model=model, messages=[{"role": "user", "content": "Say hello in five words."}])
    print("Reply:", r.choices[0].message.content)
    print("\nAll good. Start the app with: py server.py")
except Exception as e:
    print(f"That didn't work: {e}\n\nCheck the base URL, the key, and that MODEL is one of the names listed above.")
