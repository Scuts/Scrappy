import discord
from discord import app_commands
from discord.ext import commands

from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
import math
import io
import os
import logging
from datetime import date
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
@app_commands.describe(tournamentidentifier = "Identifier for the tournament", serverwide = "True to generate a schedule for all server members, false to generate a schedule for yourself.")
async def getSchedule (interaction: discord.Interaction, tournamentidentifier: str, serverwide: bool):
    await interaction.response.defer()
    logger = logging.getLogger('discordScrappy')
    fileHandler = logging.FileHandler(os.path.join(os.getenv('LOG_PATH'), date.today().strftime("%Y-%m-%d") + ".log"), 'a')
    fileHandler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    fileHandler.encoding = 'utf-8'
    fileHandler.setLevel(logging.INFO)
    if not len(logger.handlers):
        logger.addHandler(fileHandler)
    logger.setLevel(logging.INFO)

    try:
        transport = AIOHTTPTransport(url="https://api.start.gg/gql/alpha", headers={'Authorization': f'Bearer {os.getenv("STARTGG_API_KEY")}'})
        gqlClient = Client(transport=transport, fetch_schema_from_transport=True)
        
        discordIds = {}
        if serverwide:
            if "thread" in str(interaction.channel.type):
                members = await interaction.channel.fetch_members()
                threadmembers = []
                for member in members:
                    threadmembers.append(member.id)
                for member in interaction.guild.members:
                    if member.id in threadmembers:
                        discordIds[member.id] = {
                            'discordId' : member.id,
                            'nick': member.nick,
                            'pfp': member.avatar
                        }
            else:
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
                    events {
                        id
                        videogame {
                            displayName
                            images {
                                type
                                url
                                }
                        }
                    }
                }
            }"""
        )
        
        params = {"slug": tournamentidentifier}
        startGGIds = []

        authorizationsQuery = gql(
        """
        query TournamentQuery($slug: String, $page: Int, $perPage: Int) {
            tournament(slug: $slug) {
                id
                name
            participants(query: {
                page: $page
                perPage: $perPage
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
            logger.info(f'Request complete - No tournament found - Guild: {interaction.guild.name} - Tournament: {tournamentidentifier}')
            return
        tournamentImages = numAttendeesResults.get("tournament").get("images")
        bannerImageUrl = None
        if tournamentImages:
            for img in tournamentImages:
                if img.get("type") == "banner":
                    bannerImageUrl = img.get("url")

        eventImages = {}
        for event in numAttendeesResults.get("tournament").get("events"):
            eventImages[event.get("id")] = event.get("videogame")

        numAttendees = numAttendeesResults.get("tournament").get("numAttendees")

        async def getParticipants(perPage):
            for i in range(math.ceil(numAttendees / perPage) + 1):
                params = {
                    "slug": tournamentidentifier,
                    "page": i,
                    "perPage": perPage
                }
                result = await gqlClient.execute_async(authorizationsQuery, variable_values=params)
                for player in result.get("tournament").get("participants").get("nodes"):
                    if player.get("player").get("user") != None:
                        if player.get("player").get("user").get("authorizations") != None:
                            for authorization in player.get("player").get("user").get("authorizations"):
                                if authorization.get("type") == "DISCORD" and authorization.get("externalId"):
                                    startGGIds.append([player.get("player").get("id"), authorization.get("externalId"), player.get("player").get("gamerTag")])

        
        await getParticipants(241)
        await getParticipants(263)
        
        phaseGroupQuery = gql("""
            query PhaseGroupQuery($slug: String, $playerIds: [ID]) {
                tournament(slug: $slug){
                    id
                    name
                    events {
                        id
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

        if len(playerIdDict) == 0:
            await interaction.followup.send("No users in this server were found in the requested tournament. This will only find users who have bound their Start.gg account to their Discord account.")
            logger.info(f'Request complete - No users found - Guild: {interaction.guild.name} - Tournament: {tournamentidentifier}')
            return
        
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
                logger.error(f"Error on tournament match data request: {tournamentidentifier}. Exception: {str(e)}")
                return
            playerSchedule = {}
            
            for event in result.get("tournament").get("events"):
                if event.get("sets").get("nodes"):
                    videoGame = eventImages[event.get("id")]
                    for image in videoGame.get("images"):
                        if image.get("type") == "primary":
                            if videoGame.get("displayName") not in gameImages:
                                gameImage = {}
                                gameImage["url"] = image.get("url")
                                gameImages[videoGame.get("displayName")] = gameImage
                    if event.get("sets").get("nodes") and any(set.get("phaseGroup").get("startAt") for set in event.get("sets").get("nodes")):
                        for set in event.get("sets").get("nodes"):
                            if videoGame.get("displayName") + "_" + set.get("phaseGroup").get("displayIdentifier") not in playerSchedule:
                                playerSchedule[videoGame.get("displayName") + "_" + set.get("phaseGroup").get("displayIdentifier")] = {
                                    "game": videoGame.get("displayName"),
                                    "phase": set.get("phaseGroup").get("displayIdentifier"),
                                    "time": set.get("phaseGroup").get("startAt")
                                }
                    else:
                        playerSchedule[videoGame.get("displayName")]= {
                            "game": videoGame.get("displayName"),
                            "phase": None,
                            "time": event.get("startAt")
                        }

            sortedPlayerSchedule = dict(sorted(playerSchedule.items(), key = lambda item: item[1].get("time")))
            playerIdDict[playerId[0]]["schedule"] = sortedPlayerSchedule

        try:
            img = imageGeneration.generateScheduleGraphic(playerIdDict, gameImages, bannerImageUrl)
        except Exception as e:
            await interaction.followup.send(f"Error occurred when generating schedule graphic for tournament: {tournamentidentifier}.")
            logger.error(f"Error on tournament image generation: {tournamentidentifier}. Exception: {str(e)}")

        with io.BytesIO() as image_binary:
            img.save(image_binary, 'PNG')
            image_binary.seek(0)
            await interaction.followup.send(file=discord.File(fp=image_binary, filename='image.png'))
        logger.info(f'Request complete - Guild: {interaction.guild.name} - Tournament: {tournamentidentifier} - Players: {len(playerIdDict)}')
    except Exception as e:
        await interaction.followup.send(f"An unexpected error has occurred for tournament: {tournamentidentifier}. Sorry about that.")
        logger.error(f"Unexpected error. Tournament: {tournamentidentifier} - Exception: {str(e)}")
    

client.run(os.getenv('DISCORD_API_KEY'))
