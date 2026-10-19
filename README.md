# In other news

A static, magazine-style front page built from RSS feeds. No server, no database, no JavaScript.
GitHub Actions rebuilds it every hour and GitHub Pages hosts it, both free.

## Files

| File | What it does |
|---|---|
| `feeds.yaml` | Site title, settings and your list of feeds. This is the file you'll edit most. |
| `build.py` | Fetches the feeds, merges and de-duplicates them, renders `public/index.html`. |
| `templates/index.html` | The page layout and styling (all CSS is inline, one request). |
| `.github/workflows/build.yml` | Rebuilds and publishes hourly, on every push, or on demand. |

## Try it on your computer

```bash
cd ~/mylocalweb/in-other-news
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build.py
open public/index.html
```

Next time, you only need `cd ~/mylocalweb/in-other-news`, `source .venv/bin/activate` and `python build.py`.

## Put it online (GitHub Pages)

1. Create a new GitHub repository and push this folder to its `main` branch.
2. In the repo, go to **Settings → Pages** and set **Source** to **GitHub Actions**.
3. Go to the **Actions** tab, pick **Build and publish**, and click **Run workflow**.
4. After a minute your site is live at `https://<your-username>.github.io/<repo-name>/`.

From then on it refreshes every hour by itself.

## How the page is laid out

1. **The Long Read**: the newest long-form story with an image.
2. **Departments**: Ideas, Science & Nature, Politics, Australia (set in `feeds.yaml`).
3. **Video**: YouTube channels not placed in a department (hidden when empty). YouTube feeds can also go in any department, where they get a play badge.
4. **In Brief**: text-only headlines from the last 24 hours, Australia and World.

## Customising (all in `feeds.yaml`)

- **Move a source to another department:** change its `section:`.
- **Add a department:** add it under `departments:` and point feeds at its `id`.
- **Add a YouTube channel:** `url: https://www.youtube.com/feeds/videos.xml?channel_id=UC…`
  with `section: video`. The channel ID is on the channel's About page under "Share channel".
- **Split one source across departments:** use `category_map` (see the Ars Technica entry).
- **Keep a source out of the Long Read:** add `lead: false`.
- **How much to show and for how long:** the `settings:` block.
- **Colours:** the `--bg`, `--ink` and `--accent` variables at the top of `templates/index.html`.
- **Refresh rate online:** the `cron` line in `.github/workflows/build.yml`.

## Notes

- If a feed is down, the build skips it and carries on.
- GitHub pauses scheduled workflows in a public repo after 60 days with no commits. If that happens,
  just push any small change (or click Run workflow) to wake it up.
- Images are loaded straight from each publisher; nothing is copied or stored.
