import discord
from discord import app_commands
from discord.ext import commands

from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
import math
import io
import os
from dotenv import load_dotenv
import imageGeneration

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = commands.Bot(command_prefix = "!", intents=intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    try:
        synced = await client.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@client.tree.command(name="get-schedule")
@app_commands.describe(tournamentidentifier = "Identifier for the tournament", serverwide = "Get a schedule for all server members or just yourself")
async def getSchedule (interaction: discord.Interaction, tournamentidentifier: str, serverwide: bool):
    await interaction.response.defer()

    transport = AIOHTTPTransport(url="https://api.start.gg/gql/alpha", headers={'Authorization': f'Bearer {os.getenv("STARTGG_API_KEY")}'})
    gqlClient = Client(transport=transport, fetch_schema_from_transport=True)
    
    discordIds = {}
    if serverwide:
        for member in interaction.guild.members:
            discordIds[member.id] = {
                'discordId' : member.id,
                'nick': member.nick,
                'pfp': member.avatar
            }
    else:
        discordIds[interaction.user.id] = {
            'discordId' : interaction.user.id,
            'nick': interaction.user.nick,
            'pfp': interaction.user.avatar
        }

    participantNumberQuery = gql(
    """
        query TournamentQuery($slug: String) {
            tournament(slug: $slug) {
                numAttendees
                images {
                    type
                    url
                }
            }
        }"""
    )

    params = {"slug": tournamentidentifier}
    startGGIds = []

    authorizationsQuery = gql(
    """
    query TournamentQuery($slug: String, $page: Int) {
		tournament(slug: $slug) {
			id
			name
        participants(query: {
            page: $page
            perPage: 250
        })
        {
            nodes{
                player {
                    id
                    user {
                        authorizations{
                        externalId,
                        type
                    }
                }
                gamerTag
            }
        }
    }
    }
    }
    """
    )

    await interaction.followup.send("This might take a few minutes! Working...")

    numAttendeesResults = await gqlClient.execute_async(participantNumberQuery, variable_values=params)
    if not numAttendeesResults.get("tournament"):
        await interaction.followup.send(f"Tournament with identifier: \"{tournamentidentifier}\" not found. The tournament identifier is the segment just after \"tournament\" in the url. For example, the tournament identifier for: https://www.start.gg/tournament/frosty-faustings-xvii-2025/events would be frosty-faustings-xvii-2025.")
        return
    tournamentImages = numAttendeesResults.get("tournament").get("images")
    bannerImageUrl = None
    if tournamentImages:
        for img in tournamentImages:
            if img.get("type") == "banner":
                bannerImageUrl = img.get("url")

    numAttendees = numAttendeesResults.get("tournament").get("numAttendees")

    for i in range(math.ceil(numAttendees / 250)):
        params = {
            "slug": tournamentidentifier,
            "page": i
        }
        result = await gqlClient.execute_async(authorizationsQuery, variable_values=params)
        #discordIds.append(filter x: x)
        #print(result)
        for player in result.get("tournament").get("participants").get("nodes"):
            if player.get("player").get("user") != None:
                if player.get("player").get("user").get("authorizations") != None:
                    for authorization in player.get("player").get("user").get("authorizations"):
                        if authorization.get("type") == "DISCORD" and authorization.get("externalId"):
                            startGGIds.append([player.get("player").get("id"), authorization.get("externalId"), player.get("player").get("gamerTag")])

    phaseGroupQuery = gql("""
        query PhaseGroupQuery($slug: String, $playerIds: [ID]) {
            tournament(slug: $slug){
                id
                name
                events {
                    startAt
                    sets (perPage: 100, filters: {
                        playerIds: $playerIds
                    }){
                        nodes {
                            phaseGroup {
                                startAt
                                displayIdentifier
                                wave {
                                    startAt
                                }
                            }
                        }
                    }
                    videogame {
                        displayName
                        images {
                            type
                            url
                            }
                    }
                }
        }
    }
    """)

    maxPlayersReached = False
    playerIdDict = {}
    for startGGid in startGGIds:
        if not maxPlayersReached and int(startGGid[1]) in discordIds and startGGid[0] not in playerIdDict:
            if len(playerIdDict) >= 16:
                maxPlayersReached = True
                await interaction.followup.send("There are over 16 users in this server registered for the requested tournament. Only the first 16 will be shown.")
            else:
                playerIdDict[startGGid[0]]= discordIds[int(startGGid[1])]
    
    gameImages = {}
    for playerId in playerIdDict.items():
        params = {
            "slug": tournamentidentifier,
            "playerIds": [playerId[0]]
        }
        
        try:
            result = await gqlClient.execute_async(phaseGroupQuery, variable_values=params)
        except Exception as e:
            await interaction.followup.send(f"Error occurred when trying to get match data for tournament: {tournamentidentifier}.")
            return
        playerSchedule = {}
        
        for event in result.get("tournament").get("events"):
            if event.get("sets").get("nodes"):
                for image in event.get("videogame").get("images"):
                    if image.get("type") == "primary":
                        if event.get("videogame").get("displayName") not in gameImages:
                            gameImage = {}
                            gameImage["url"] = image.get("url")
                            gameImages[event.get("videogame").get("displayName")] = gameImage
                if event.get("sets").get("nodes") and any(set.get("phaseGroup").get("startAt") for set in event.get("sets").get("nodes")):
                    for set in event.get("sets").get("nodes"):
                        if event.get("videogame").get("displayName") + "_" + set.get("phaseGroup").get("displayIdentifier") not in playerSchedule:
                            playerSchedule[event.get("videogame").get("displayName") + "_" + set.get("phaseGroup").get("displayIdentifier")] = {
                                "game": event.get("videogame").get("displayName"),
                                "phase": set.get("phaseGroup").get("displayIdentifier"),
                                "time": set.get("phaseGroup").get("startAt")
                            }
                else:
                    playerSchedule[event.get("videogame").get("displayName")]= {
                        "game": event.get("videogame").get("displayName"),
                        "phase": None,
                        "time": event.get("startAt")
                    }

        sortedPlayerSchedule = dict(sorted(playerSchedule.items(), key = lambda item: item[1].get("time")))
        playerIdDict[playerId[0]]["schedule"] = sortedPlayerSchedule

    img = imageGeneration.generateScheduleGraphic(playerIdDict, gameImages, bannerImageUrl)

    with io.BytesIO() as image_binary:
        img.save(image_binary, 'PNG')
        image_binary.seek(0)
        await interaction.followup.send(file=discord.File(fp=image_binary, filename='image.png'))    

client.run(os.getenv('DISCORD_API_KEY'))
