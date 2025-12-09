import io
import os
import asyncio
import httpx
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# ✅ BD SERVER FIXES: API URL এবং Region সেট করা হলো
# Prince LK-Team API ব্যবহার করা হয়েছে, যা কোনো API Key ছাড়াই কাজ করে।
INFO_API_URL = "https://info-ob49.vercel.app/api/account"
FF_REGION = "BD" # <--- নিশ্চিত BD (Bangladesh) সার্ভারের জন্য সেট করা হয়েছে
# ------------------------------------------------------------------

FONT_FILE = "NotoSans-Bold.ttf"

client = httpx.AsyncClient(
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=10.0,
    follow_redirects=True
)

process_pool = ThreadPoolExecutor(max_workers=4)

def load_unicode_font(size):
    try:
        font_path = os.path.join(os.path.dirname(__file__), FONT_FILE)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()
    except:
        return ImageFont.load_default()

async def fetch_image_bytes(item_id):
    if not item_id or str(item_id) == "0" or item_id is None:
        return None

    item_id = str(item_id)
    
    # এটি Free Fire-এর অ্যাসেট লোড করার জন্য দরকারি
    # আপনার কোডে এই অংশটি ঠিক আছে
    for repo_num in range(1, 7):
        if repo_num == 1: 
            batch_start, batch_end = 1, 7
        else:
            batch_start = (repo_num - 1) * 7 + 1
            batch_end = repo_num * 7
            
        repo_name = f"ff-repo-{repo_num}.vercel.app"
        
        for batch_num in range(batch_start, batch_end + 1):
            url = f"https://{repo_name}/{item_id}/batch_{batch_num}.png"
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.content
            except httpx.ConnectError:
                # If one repo fails, try the next
                break
            except Exception:
                continue
    return None


# (process_banner_image ফাংশন, এটি পরিবর্তন করার দরকার নেই)
def process_banner_image(banner_data, avatar_bytes, banner_bytes, pin_bytes):
    # Dummy function for placehoder/logic, replace with your actual PIL logic
    
    # The actual image processing logic from your original code would go here
    # Since I don't have the full original 'process_banner_image' code, 
    # I am assuming it works and placing a placeholder.
    
    # --- Start of Placeholder PIL Logic ---
    try:
        # Load Images
        banner_img = Image.open(io.BytesIO(banner_bytes or b'')).resize((1024, 512)) if banner_bytes else Image.new('RGB', (1024, 512), color = '#202020')
        
        if avatar_bytes:
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).resize((200, 200)).convert("RGBA")
            banner_img.paste(avatar_img, (50, 50), avatar_img)
        
        draw = ImageDraw.Draw(banner_img)
        
        # Load Font
        font_30 = load_unicode_font(30)
        font_48 = load_unicode_font(48)
        
        # Draw Text
        draw.text((300, 60), banner_data.get("AccountName", "Player Not Found"), fill=(255, 255, 255), font=font_48)
        draw.text((300, 130), f"Level: {banner_data.get('AccountLevel', '?')}", fill=(200, 200, 200), font=font_30)
        draw.text((300, 180), f"Guild: {banner_data.get('GuildName', 'No Guild')}", fill=(200, 200, 200), font=font_30)

        if pin_bytes:
            pin_img = Image.open(io.BytesIO(pin_bytes)).resize((64, 64)).convert("RGBA")
            banner_img.paste(pin_img, (900, 40), pin_img)

        # Save to BytesIO
        img_io = io.BytesIO()
        banner_img.save(img_io, format='PNG')
        img_io.seek(0)
        return img_io
    except Exception as e:
        print(f"PIL Error: {e}")
        # Fallback for missing assets
        img_io = io.BytesIO()
        Image.new('RGB', (1024, 512), color = 'red').save(img_io, format='PNG')
        img_io.seek(0)
        return img_io
    # --- End of Placeholder PIL Logic ---


@app.get("/profile")
async def get_banner(uid: str):
    if not uid:
        raise HTTPException(status_code=400, detail="UID required")

    try:
        # --------------------------------------------------------------------------
        # ✅ FIX 2: Region parameter-টি যোগ করা হলো
        resp = await client.get(f"{INFO_API_URL}?uid={uid}&region={FF_REGION}") 
        # --------------------------------------------------------------------------
        
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Info API Error")
            
        data = resp.json()
        
        acc = data.get("AccountInfo", data)
        guild = data.get("GuildInfo", {})
        
        # Run image fetching concurrently
        avatar_task = fetch_image_bytes(acc.get("AccountAvatarId") or acc.get("headPic"))
        banner_task = fetch_image_bytes(acc.get("AccountBannerId") or acc.get("bannerId"))
        
        pin_id = acc.get("pinId") or acc.get("title")
        pin_task = fetch_image_bytes(pin_id) if (pin_id and str(pin_id) != "0") else asyncio.sleep(0)

        results = await asyncio.gather(avatar_task, banner_task, pin_task)
        avatar_bytes, banner_bytes, pin_bytes = results[0], results[1], results[2]
        
        if pin_bytes is None: pin_bytes = b''

        loop = asyncio.get_event_loop()
        banner_data = {
            "AccountLevel": acc.get("AccountLevel") or acc.get("level"),
            "AccountName": acc.get("AccountName") or acc.get("nickname"),
            "GuildName": guild.get("GuildName") or guild.get("clanName") or ""
        }
        
        img_io = await loop.run_in_executor(
            process_pool, 
            process_banner_image, 
            banner_data, avatar_bytes, banner_bytes, pin_bytes
        )
        
        return Response(content=img_io.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=300"})

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import uvicorn
    # Local run command for testing
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
