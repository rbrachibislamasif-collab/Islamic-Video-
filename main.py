import os, sys, json, time, random, subprocess
import requests

G = "v26.0"
E = os.environ.get
FB_PAGE_ID, FB_PAGE_TOKEN = E("FB_PAGE_ID"), E("FB_PAGE_TOKEN")
IG_USER_ID = E("IG_USER_ID")
GEMINI_KEY, PIXABAY_KEY = E("GEMINI_API_KEY"), E("PIXABAY_API_KEY")
YT_ID, YT_SECRET, YT_REFRESH = E("YT_CLIENT_ID"), E("YT_CLIENT_SECRET"), E("YT_REFRESH_TOKEN")
MODELS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-flash-lite-latest"]
PRIVACY = "public"
NICHE = E("NICHE") or "ইসলামের শিক্ষণীয় বিষয়"
ANGLES = ["আখলাক ও সুন্দর চরিত্র", "নবী-রাসূলদের শিক্ষণীয় ঘটনা", "দোয়া ও যিকির", "সবর ও শোকর",
          "পিতা-মাতার হক ও আত্মীয়তা", "সততা ও আমানত", "সালাত ও ইবাদতের গুরুত্ব", "আল্লাহর সৃষ্টি নিয়ে চিন্তা",
          "সাহাবীদের জীবনের শিক্ষা", "ক্ষমা, তওবা ও আল্লাহর রহমত"]
os.makedirs("work", exist_ok=True)


def check(r):
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text[:400]}")
    return r


def make_content():
    prompt = (
        f"তুমি একটি বাংলা ইসলামিক শিক্ষামূলক পেজের কনটেন্ট লেখক। বিষয়: {NICHE}। এবারের দিক: {random.choice(ANGLES)}। "
        "কঠোর নিয়ম: কুরআনের আয়াত বা হাদিস তখনই উল্লেখ করবে যখন তুমি পুরোপুরি নিশ্চিত এবং হাদিস অবশ্যই সহিহ; "
        "রেফারেন্স (সূরা ও আয়াত নম্বর, বা হাদিস গ্রন্থের নাম) সাথে দেবে। নিশ্চিত না হলে সরাসরি উদ্ধৃতি না দিয়ে সাধারণ নৈতিক শিক্ষা লেখো। "
        "কিছু বানিয়ে বা দুর্বল ও জাল হাদিস লিখবে না। ফতোয়া, মাজহাব বা ফেরকা-সংক্রান্ত বিতর্ক, রাজনীতি এড়িয়ে চলবে। "
        "ভাষা সহজ, বিনয়ী ও ইতিবাচক। শেষে একটি ছোট শিক্ষা বা দোয়া দেবে। "
        "একটি ছোট ভিডিওর জন্য শুধু JSON দাও: "
        '{"title": "বাংলা শিরোনাম (৬০ অক্ষরের মধ্যে)", '
        '"caption": "বাংলায় ৩-৪ লাইনের শিক্ষণীয় ক্যাপশন, রেফারেন্সসহ", '
        '"hashtags": ["৫টি হ্যাশট্যাগ"], '
        '"query": "Pixabay ভিডিও সার্চের জন্য ১-২ শব্দের ইংরেজি কীওয়ার্ড, শুধু প্রকৃতি, আকাশ, মসজিদ, কুরআন, কাবা, বৃষ্টি, সূর্যোদয় জাতীয় (মানুষের ছবি ছাড়া)"}'
    )
    r = None
    for m in MODELS:
        try:
            r = check(requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m.strip()}:generateContent",
                params={"key": GEMINI_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json"}},
                timeout=90))
            print("Gemini মডেল:", m)
            break
        except Exception as e:
            print("মডেল ব্যর্থ:", m, str(e)[:150])
    if r is None:
        raise RuntimeError("কোনো Gemini মডেল কাজ করেনি")
    d = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    if isinstance(d, list):
        d = d[0]
    d["hashtags"] = [h if h.startswith("#") else "#" + h.replace(" ", "") for h in d.get("hashtags", [])]
    return d


def make_video(query):
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": PIXABAY_KEY, "q": query, "per_page": 50, "safesearch": "true"}, timeout=60)
    hits = check(r).json().get("hits", [])
    good = [h for h in hits if 5 <= h.get("duration", 0) <= 60] or hits
    if not good:
        raise RuntimeError("Pixabay এ ভিডিও পাওয়া যায়নি: " + query)
    v = random.choice(good)["videos"]
    url = next(v[k]["url"] for k in ("large", "medium", "small", "tiny") if v.get(k, {}).get("url"))
    raw, out = "work/raw.mp4", "work/post.mp4"
    with requests.get(url, stream=True, timeout=120) as s:
        check(s)
        with open(raw, "wb") as f:
            for c in s.iter_content(1 << 20):
                f.write(c)
    # ৯:১৬ ভার্টিক্যাল (Shorts/Reels), সর্বোচ্চ ৩০ সেকেন্ড
    subprocess.run(["ffmpeg", "-y", "-i", raw, "-t", "30",
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
                    "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", out],
                   check=True, capture_output=True)
    return out


def post_youtube(path, d, text):
    tok = check(requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": YT_ID, "client_secret": YT_SECRET,
        "refresh_token": YT_REFRESH, "grant_type": "refresh_token"}, timeout=60)).json()["access_token"]
    meta = {"snippet": {"title": (d["title"][:88] + " #Shorts")[:100], "description": text + "\n#Shorts",
                        "categoryId": "24"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    size = os.path.getsize(path)
    r = check(requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        data=json.dumps(meta, ensure_ascii=False).encode("utf-8"), timeout=60))
    with open(path, "rb") as f:
        u = check(requests.put(r.headers["Location"], data=f,
                               headers={"Content-Type": "video/mp4"}, timeout=900))
    return u.json()["id"]


def post_facebook(path, d, text):
    with open(path, "rb") as f:
        r = check(requests.post(f"https://graph-video.facebook.com/{G}/{FB_PAGE_ID}/videos",
                                data={"access_token": FB_PAGE_TOKEN, "title": d["title"], "description": text},
                                files={"source": f}, timeout=900))
    return r.json()["id"]


def post_instagram(path, d, text):
    r = check(requests.post(f"https://graph.facebook.com/{G}/{IG_USER_ID}/media",
                            data={"media_type": "REELS", "upload_type": "resumable",
                                  "caption": text, "access_token": FB_PAGE_TOKEN}, timeout=60)).json()
    cid = r["id"]
    uri = r.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{G}/{cid}"
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        check(requests.post(uri, headers={"Authorization": "OAuth " + FB_PAGE_TOKEN,
                                          "offset": "0", "file_size": str(size)}, data=f, timeout=900))
    for _ in range(40):
        s = requests.get(f"https://graph.facebook.com/{G}/{cid}",
                         params={"fields": "status_code,status", "access_token": FB_PAGE_TOKEN}, timeout=60).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError("Instagram প্রসেসিং এরর: " + str(s))
        time.sleep(10)
    else:
        raise RuntimeError("Instagram প্রসেসিং এর সময় শেষ")
    p = check(requests.post(f"https://graph.facebook.com/{G}/{IG_USER_ID}/media_publish",
                            data={"creation_id": cid, "access_token": FB_PAGE_TOKEN}, timeout=60))
    return p.json()["id"]


def main():
    d = make_content()
    print("কনটেন্ট:", json.dumps(d, ensure_ascii=False))
    path = make_video(d["query"])
    text = d["caption"] + "\n\n" + " ".join(d["hashtags"])
    results = {}
    for name, fn in (("YouTube", post_youtube), ("Facebook", post_facebook), ("Instagram", post_instagram)):
        try:
            results[name] = "✅ " + str(fn(path, d, text))
        except Exception as e:
            results[name] = "❌ " + str(e)
    for k, v in results.items():
        print(k, v)
    if any(v.startswith("❌") for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
