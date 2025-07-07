import discord
import os
import aiohttp
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta

# --- Configuration ---
# Load environment variables from .env file
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LM_STUDIO_ENDPOINT = os.getenv("LM_STUDIO_ENDPOINT")
COOLDOWN_SECONDS = 15 # Cooldown period for each user

# --- Bot Setup ---
# Define necessary intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

# Bot instance with a command prefix (though we'll use on_message)
bot = discord.Client(intents=intents)

# --- Data Structures for Rate Limiting ---
# Tracks the timestamp of the last request for each user
user_cooldowns = {}
# Tracks users who are currently waiting for a response to prevent concurrent requests
users_awaiting_response = set()

# --- Helper Function to Get AI Response ---
async def get_ai_response(prompt: str) -> str:
    """
    Sends a prompt to the LM Studio API and returns the AI's response.
    """
    if not LM_STUDIO_ENDPOINT:
        return "Error: The LM Studio API endpoint is not configured."

    headers = {"Content-Type": "application/json"}
    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(LM_STUDIO_ENDPOINT, headers=headers, data=json.dumps(payload)) as response:
                if response.status == 200:
                    data = await response.json()
                    # Check if the expected keys exist in the response
                    if "choices" in data and data["choices"] and "message" in data["choices"][0] and "content" in data["choices"][0]["message"]:
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        print(f"Unexpected API response format: {data}")
                        return "Sorry, I received an unexpected response from the AI."
                else:
                    error_text = await response.text()
                    print(f"API Error: Status {response.status} - {error_text}")
                    return f"Sorry, the AI service returned an error (Status: {response.status})."

    except aiohttp.ClientConnectorError:
        print("Error: Could not connect to the LM Studio API endpoint.")
        return "Sorry, I can't reach the AI at the moment. Please make sure the local server is running."
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return "An unexpected error occurred while trying to contact the AI."

# --- Bot Events ---
@bot.event
async def on_ready():
    """
    Event handler for when the bot has successfully connected to Discord.
    """
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('Bot is ready and listening for messages.')
    print('------')

@bot.event
async def on_message(message: discord.Message):
    """
    Event handler for when a message is sent in a channel the bot can see.
    """
    # 1. Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # 2. Check if the message triggers the bot
    is_command = message.content.startswith('!ask')
    is_mention = bot.user.mentioned_in(message)

    if not is_command and not is_mention:
        return

    # 3. Flood & Spam Protection
    user_id = message.author.id

    # Check if user is already waiting for a response
    if user_id in users_awaiting_response:
        await message.channel.send("Please wait for your previous request to complete.", delete_after=10)
        return

    # Check if user is on cooldown
    if user_id in user_cooldowns:
        time_since_last_request = datetime.now() - user_cooldowns[user_id]
        if time_since_last_request < timedelta(seconds=COOLDOWN_SECONDS):
            remaining_time = COOLDOWN_SECONDS - time_since_last_request.total_seconds()
            await message.channel.send(f"You're on a cooldown. Please wait {remaining_time:.1f} more seconds.", delete_after=10)
            return

    # 4. Process the prompt
    if is_command:
        # For `!ask what is...`, prompt is "what is..."
        prompt = message.content[len('!ask '):].strip()
    elif is_mention:
        # For `@Bot what is...`, prompt is "what is..."
        # We remove the mention from the content
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()

    if not prompt:
        await message.channel.send("Please provide a prompt after the command or mention!", delete_after=10)
        return

    # 5. Get and send the AI response
    users_awaiting_response.add(user_id)
    try:
        async with message.channel.typing():
            # Get response from the local AI
            ai_response = await get_ai_response(prompt)
            # Send the response back to the Discord channel
            await message.channel.send(ai_response)
            # Update the user's cooldown timestamp after a successful request
            user_cooldowns[user_id] = datetime.now()
    finally:
        # Ensure the user is removed from the set, even if an error occurs
        users_awaiting_response.remove(user_id)


# --- Run the Bot ---
if __name__ == "__main__":
    if DISCORD_TOKEN is None:
        print("FATAL ERROR: DISCORD_TOKEN is not set in the .env file.")
    elif LM_STUDIO_ENDPOINT is None:
        print("FATAL ERROR: LM_STUDIO_ENDPOINT is not set in the .env file.")
    else:
        bot.run(DISCORD_TOKEN)
