from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
import requests
import os
from dotenv import load_dotenv
import datetime

cell_width = 128
cell_height = 96
pfp_height = cell_height
vertical_margin = 48
horizontal_margin = 48
footer_height = 48
cell_margin = 8
banner_height = 192
textShadowOffset = 2
dateBarHeight = 36

backgroundColor = (252, 243, 230, 255)
accentColor1 = (67, 118, 163, 255)
accentColor2 = (232, 140, 49, 255)

clr_white = (255, 255, 255, 255)
clr_black = (0, 0, 0, 255)

load_dotenv()
font = ImageFont.truetype(os.getenv("FONT_PATH"), 32)
smallFont = ImageFont.truetype(os.getenv("FONT_PATH"), 20)

def generateScheduleGraphic(scheduleDict, gameImagesDict, bannerImageUrl):
    uniqueTimeSlots = []
    uniqueDays = []

    for playerId, schedule in scheduleDict.items():
        if schedule.get("schedule"):
            for poolIdentifier, poolDict in schedule.get("schedule").items():
                if poolDict.get('time') not in uniqueTimeSlots:
                    uniqueTimeSlots.append(poolDict.get('time'))
    
    uniqueDays = []
    for timestamp in uniqueTimeSlots:
        if not datetime.datetime.fromtimestamp(int(timestamp)).date() in uniqueDays:
            uniqueDays.append(datetime.datetime.fromtimestamp(int(timestamp)).date())

    uniqueDays = sorted(uniqueDays)
    uniqueTimeSlots = sorted(uniqueTimeSlots)

    for key, value in gameImagesDict.items():
        value["image"] = Image.open(requests.get(value.get("url"), stream=True).raw)

    totalImageWidth = cell_width*(len(scheduleDict) + 1) + (cell_margin * len(scheduleDict)) + (horizontal_margin * 2)
    totalImageHeight = banner_height + ((len(uniqueTimeSlots)) * (cell_height + cell_margin)) + (len(uniqueDays) * (dateBarHeight + cell_margin)) + pfp_height + (vertical_margin * 2) + footer_height

    background = Image.new('RGBA',(totalImageWidth, totalImageHeight), backgroundColor)
    i = 0

    if bannerImageUrl:
        banner_im = Image.open(requests.get(bannerImageUrl, stream=True).raw)
        banner_im_width, banner_im_height = banner_im.size
        banner_desired_width = totalImageWidth - (2 * horizontal_margin)
        desiredRatio = (float(banner_desired_width)) / (float(banner_height))
        bannerRatio = (float(banner_im_width)) / (float(banner_im_height))

        if desiredRatio > bannerRatio:
            banner_im_re = banner_im.resize(size=(banner_desired_width, (int) (banner_desired_width/bannerRatio)),resample=Image.Resampling.NEAREST)
        else:
            banner_im_re = banner_im.resize(size=((int) (banner_height*bannerRatio), banner_height),resample=Image.Resampling.NEAREST)
        banner_im_width, banner_im_height = banner_im_re.size
        new_dims = ((banner_im_width/2) - (banner_desired_width/2), 
                        (banner_im_height/2) - (banner_height/2), 
                        (banner_im_width/2) +  (banner_desired_width/2), 
                        (banner_im_height/2) + (banner_height/2))
        banner_cr = banner_im_re.crop(new_dims)

        background.paste(banner_cr, (horizontal_margin, vertical_margin))

    draw = ImageDraw.Draw(background)
    for kvp in scheduleDict.items():
        player = kvp[1]
        im = Image.open(requests.get(player.get("pfp"), stream=True).raw)
        im_re = im.resize(size=(cell_width, cell_width),resample=Image.Resampling.NEAREST)
        im_cr = im_re.crop((0, int((cell_width/2) - (pfp_height/2)), cell_width, int((cell_width/2) + (pfp_height/2))))
        background.paste(im_cr,((i+1) * (cell_width + cell_margin) + horizontal_margin, vertical_margin + banner_height + cell_margin))

        for poolIdentifier, pool in player.get("schedule").items():
            game_im = gameImagesDict.get(pool.get("game")).get("image")
            game_width, game_height = game_im.size
            game_re = game_im.resize(size=(cell_width, int(cell_width * float(game_height/game_width))))
            game_width, game_height = game_re.size
            midpt = game_height/2
            game_cr = game_re.crop((0, int(midpt - (cell_height/2)), cell_width, int(midpt + (cell_height/2))))
            timeSlotIndex = uniqueTimeSlots.index(pool.get("time"))
            dayIndex = uniqueDays.index(datetime.datetime.fromtimestamp(pool.get("time")).date()) + 1
            timeSlotIndex = timeSlotIndex
            cellX = (i + 1) * (cell_width + cell_margin) + horizontal_margin
            cellY = timeSlotIndex * (cell_height + cell_margin) + dayIndex * (dateBarHeight + cell_margin) + pfp_height + vertical_margin + banner_height + (cell_margin * 2)
            background.paste(game_cr,(cellX, cellY))
            if pool.get("phase"):
                draw.text(xy=(int(cell_width/2) + cellX + textShadowOffset, cellY + int(cell_height/2) + textShadowOffset), text = pool.get('phase'), font=font, anchor="mm", fill=clr_black) 
                draw.text(xy=(int(cell_width/2) + cellX, cellY + int(cell_height/2)), text = pool.get('phase'), font=font, anchor="mm", fill=clr_white) 
        i+=1
    rectX = horizontal_margin
    rectY = vertical_margin + banner_height + cell_margin
    fill_color = accentColor1
    dayIndex = 0
    for day in uniqueDays:
        rectX = horizontal_margin
        previousTimeSlots = sum(1 for time in uniqueTimeSlots if datetime.datetime.fromtimestamp(int(time)).date() < day)
        rectY = (previousTimeSlots * (cell_height + cell_margin)) + (dayIndex * (dateBarHeight + cell_margin)) + pfp_height + vertical_margin + banner_height + (cell_margin * 2) 
        draw.rectangle(xy=(rectX, rectY, rectX + (totalImageWidth - (2 * horizontal_margin)), rectY + dateBarHeight), fill=clr_black) 
        draw.text(xy=(int(cell_width/2) + horizontal_margin, rectY + int(dateBarHeight/2)), text = day.strftime('%m-%d'), font=font, anchor="mm", fill=clr_white) 
        dayIndex+=1     
    i = 0
    for time in uniqueTimeSlots:
        day = datetime.datetime.fromtimestamp(int(time)).date()

        dayIndex = uniqueDays.index(day) + 1
        rectX = horizontal_margin
        rectY = (i * (cell_height + cell_margin)) + (dayIndex * (dateBarHeight + cell_margin)) + pfp_height + vertical_margin + banner_height + (cell_margin * 2)
        if i%2 == 1:
            fill_color = accentColor1
        else:
            fill_color = accentColor2
        draw.rectangle(xy=(rectX, rectY, rectX + cell_width, rectY + cell_height), fill=fill_color)

        draw.text(xy=(int(cell_width/2) + horizontal_margin + textShadowOffset, rectY + int(cell_height/2) + textShadowOffset), text = str(datetime.datetime.fromtimestamp(time).strftime('%H:%M')), font=font, anchor="mm", fill=clr_black)
        draw.text(xy=(int(cell_width/2) + horizontal_margin, rectY + int(cell_height/2)), text = str(datetime.datetime.fromtimestamp(time).strftime('%H:%M')), font=font, anchor="mm", fill=clr_white)
        i+=1
    footerText = f"Generated at: {datetime.datetime.now().strftime('%y-%m-%d %I:%M%p')}"
    draw.text(xy=(totalImageWidth - horizontal_margin + textShadowOffset, totalImageHeight - footer_height + textShadowOffset), text=footerText, anchor="rm", fill=clr_black,font=smallFont)
    draw.text(xy=(totalImageWidth - horizontal_margin, totalImageHeight - footer_height), text=footerText, anchor="rm", fill=clr_white,font=smallFont)
    return background
